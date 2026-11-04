"""Commit-exact GitHub materialization using Studio's isolated, hook-free Git adapter."""
import configparser
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project-git'))
from git import Git
from github import GitHub
from common import ProjectFault

MAX_FILES = 100000
MAX_BYTES = 2 * 1024 ** 3
MAX_FILE = 256 * 1024 ** 2


def relative(value):
    p = PurePosixPath(value)
    # Source snapshots retain POSIX fixture names, including non-UTF8 bytes via
    # surrogateescape. Paths never become command arguments or published names.
    if (not value or p.is_absolute() or str(p) != value or '\0' in value
            or len(os.fsencode(value)) > 4096
            or any(part in ('', '.', '..', '.git') or len(os.fsencode(part)) > 255 for part in p.parts)):
        raise ProjectFault('Unsupported repository path; links and private Git paths cannot be materialized.', 409)
    return value


def github_url(value):
    if not isinstance(value, str) or not re.fullmatch(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', value):
        raise ProjectFault('A submodule requires an explicit HTTPS GitHub repository URL.', 409)
    result = value[:-4] if value.endswith('.git') else value
    if any(p in ('.', '..') for p in result.split('/')[-2:]):
        raise ProjectFault('Invalid submodule repository.', 409)
    return result.lower()


class SourceGit(Git):
    def command(self, args, auth=None):
        command = super().command(args, auth)
        index = command.index('/usr/bin/git') + 1
        command[index:index] = ['-c', 'transfer.fsckObjects=true', '-c', 'fetch.fsckObjects=true']
        return command


class Checkout:
    def __init__(self, stage, github_directory, connection_id=None, progress=lambda **value: None):
        self.stage = Path(stage)
        self.github_directory = Path(github_directory)
        self.connection_id = connection_id
        self.github = GitHub(github_directory, connection_id) if connection_id else None
        self.progress = progress
        self.files = []
        self.repositories = []
        self.total = 0
        self.visiting = set()

    def client(self, url, work):
        owner, name = url.split('/')[-2:]
        repository_id = None
        if self.github:
            repository = self.github.repository(owner, name)
            if not repository['read']:
                raise ProjectFault('The GitHub connection cannot read this repository.', 403)
            repository_id = repository['id']
            self.github.assert_current()
        key = hashlib.sha256(url.encode()).hexdigest()
        base = self.stage / 'Git' / key
        base.mkdir(parents=True, mode=0o700, exist_ok=True)
        for name in ('Objects', 'Temporary'):
            (base / name).mkdir(mode=0o700, exist_ok=True)
        git = SourceGit(base / 'Objects', work, base / 'Temporary', self.github.token if self.github else None)
        git.init()
        return git, repository_id

    def resolve(self, url, ref):
        url = github_url(url)
        workspace = self.stage / 'Repository'
        workspace.mkdir(mode=0o700, exist_ok=True)
        git, repository_id = self.client(url, workspace)
        if re.fullmatch('[a-f0-9]{40}', ref or ''):
            commit = ref
        else:
            names = (['HEAD'] if not ref else [ref, ref + '^{}'] if ref.startswith(('refs/heads/', 'refs/tags/'))
                     else ['refs/heads/' + ref, 'refs/tags/' + ref, 'refs/tags/' + ref + '^{}'])
            rows = git.text('ls-remote', '--', url + '.git', *names, timeout=90).splitlines()
            matches = {}
            for line in rows:
                oid, name = line.split('\t', 1)
                if not re.fullmatch('[a-f0-9]{40}', oid):
                    raise ProjectFault('GitHub returned an invalid source identity.', 502)
                matches[name] = oid
            commit = next((matches.get(name + '^{}') or matches[name] for name in names if name in matches), None)
            if not commit:
                raise ProjectFault('The selected GitHub branch or tag is unavailable.', 404)
        return commit, repository_id

    def write_blob(self, root, path, mode, oid, data, size):
        relative(path)
        if len(data) != size or hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest() != oid:
            raise ProjectFault('The downloaded Git blob differs from its original identity.', 503)
        lfs = None
        if data.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
            match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([a-f0-9]{64})\nsize ([0-9]+)\n?', data)
            if match:
                lfs = dict(sha256=match[1].decode('ascii'), bytes=int(match[2]), materialized=False)
        target = root / path
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if target.parent.resolve(strict=True) != target.parent:
            raise ProjectFault('The repository destination changed.', 409)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700 if mode == '100755' else 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        self.files.append(dict(path=target.relative_to(self.stage / 'Repository').as_posix(), bytes=size,
                               sha256=hashlib.sha256(data).hexdigest(), gitBlob=oid, gitMode=mode,
                               executable=mode == '100755', inertLink=mode == '120000', lfs=lfs))

    def large_blob(self, git, root, path, mode, oid, size):
        relative(path)
        target = root / path
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if target.parent.resolve(strict=True) != target.parent:
            raise ProjectFault('The repository destination changed.', 409)
        env = dict(PATH='/usr/bin:/bin', HOME='/home', LANG='C.UTF-8', GIT_CONFIG_NOSYSTEM='1',
                   GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0', GIT_ALLOW_PROTOCOL='https')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700 if mode == '100755' else 0o600)
        with os.fdopen(fd, 'wb') as stream:
            child = subprocess.Popen(git.command(['cat-file', 'blob', oid]), env=env,
                                     stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
            try:
                child.wait(timeout=120)
            except BaseException:
                os.killpg(child.pid, 9)
                child.wait()
                raise
        if child.returncode or target.stat().st_size != size:
            raise ProjectFault('The large Git blob was not confirmed.', 503)
        h1 = hashlib.sha1(b'blob ' + str(size).encode() + b'\0')
        h2 = hashlib.sha256()
        with target.open('rb') as stream:
            while data := stream.read(65536):
                h1.update(data)
                h2.update(data)
        if h1.hexdigest() != oid:
            raise ProjectFault('The large Git blob identity differs.', 503)
        self.files.append(dict(path=target.relative_to(self.stage / 'Repository').as_posix(), bytes=size,
                               sha256=h2.hexdigest(), gitBlob=oid, gitMode=mode,
                               executable=mode == '100755', inertLink=mode == '120000'))

    def materialize(self, url, commit, target=None, depth=0):
        url = github_url(url)
        if not re.fullmatch('[a-f0-9]{40}', commit or '') or depth > 6 or (url, commit) in self.visiting:
            raise ProjectFault('Unsupported or cyclic submodule source.', 409)
        self.visiting.add((url, commit))
        target = Path(target) if target is not None else self.stage / 'Repository'
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        git, repository_id = self.client(url, target)
        self.progress(phase='downloading', repository=url, files=len(self.files), bytes=self.total)
        git.run('fetch', '--depth=1', '--no-tags', '--no-recurse-submodules', url + '.git', commit, timeout=300)
        if git.text('rev-parse', '--verify', 'FETCH_HEAD^{commit}') != commit:
            raise ProjectFault('GitHub returned another source commit.', 503)
        raw = git.run('ls-tree', '-r', '-z', '--full-tree', commit)[0]
        entries, modules = [], []
        for item in raw.split(b'\0'):
            if not item:
                continue
            header, path = item.split(b'\t', 1)
            mode, kind, oid = header.decode('ascii').split(' ')
            path = relative(path.decode('utf8', errors='surrogateescape'))
            if not re.fullmatch('[a-f0-9]{40}', oid):
                raise ProjectFault('Invalid Git object identity.', 503)
            if mode == '160000' and kind == 'commit':
                modules.append((path, oid))
            elif mode in ('100644', '100755', '120000') and kind == 'blob':
                # Preserve the exact Git payload/mode of hostile symlink fixtures
                # as inert regular data; never create a link into the host.
                entries.append((path, mode, oid))
            else:
                raise ProjectFault('Special source entries are unsupported; no unsafe checkout was performed.', 409)
        if len(self.files) + len(entries) > MAX_FILES:
            raise ProjectFault('Skill repositories exceed the 100000-file source limit.', 409)
        query = ('\n'.join(x[2] for x in entries) + ('\n' if entries else '')).encode()
        sizes = git.run('cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)', data=query)[0].decode().splitlines()
        if len(sizes) != len(entries):
            raise ProjectFault('The Git inventory is incomplete.', 503)
        batch, batch_bytes = [], 0

        def flush():
            nonlocal batch, batch_bytes
            if not batch:
                return
            output = io.BytesIO(git.run('cat-file', '--batch', data=('\n'.join(x[2] for x in batch) + '\n').encode())[0])
            for path, mode, oid, size in batch:
                if output.readline() != f'{oid} blob {size}\n'.encode():
                    raise ProjectFault('A Git source response has an unexpected identity.', 503)
                self.write_blob(target, path, mode, oid, output.read(size), size)
                if output.read(1) != b'\n':
                    raise ProjectFault('A Git source response is incomplete.', 503)
            if output.read(1):
                raise ProjectFault('A Git source response contains unexpected bytes.', 503)
            batch, batch_bytes = [], 0
            self.progress(phase='materializing', files=len(self.files), bytes=self.total)

        for entry, info in zip(entries, sizes, strict=True):
            oid, kind, raw_size = info.split(' ')
            size = int(raw_size)
            if oid != entry[2] or kind != 'blob' or not 0 <= size <= MAX_FILE:
                raise ProjectFault('A source object exceeds its type or byte limit.', 409)
            self.total += size
            if self.total > MAX_BYTES:
                raise ProjectFault('Skill sources exceed the 2 GiB expanded limit.', 409)
            if size > 24 * 1024 * 1024:
                flush()
                self.large_blob(git, target, *entry, size)
            else:
                if batch_bytes + size > 24 * 1024 * 1024:
                    flush()
                batch.append((*entry, size))
                batch_bytes += size
        flush()
        self.repositories.append(dict(repository=url, commit=commit, repositoryId=repository_id,
                                      path=target.relative_to(self.stage / 'Repository').as_posix()))
        if modules:
            module_file = target / '.gitmodules'
            if not module_file.is_file() or module_file.stat().st_size > 1024 * 1024:
                raise ProjectFault('Submodule declarations are missing or too large.', 409)
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            parser.read_string(module_file.read_text())
            links = {}
            for section in parser.sections():
                path = relative(parser.get(section, 'path'))
                if path in links:
                    raise ProjectFault('Duplicate submodule declaration.', 409)
                links[path] = github_url(parser.get(section, 'url'))
            for path, oid in modules:
                if path not in links:
                    raise ProjectFault('A pinned submodule has no explicit GitHub source.', 409)
                self.materialize(links[path], oid, target / path, depth + 1)
        if self.github:
            self.github.assert_current()
        self.visiting.remove((url, commit))
        return dict(files=sorted(self.files, key=lambda x: x['path']), repositories=self.repositories,
                    totalBytes=self.total, tokenRevision=self.github.token_revision if self.github else None)
