#!/usr/bin/env python3
"""One originally admitted source job. No repository hooks or installers execute."""
from contextlib import closing
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys

spec = importlib.util.spec_from_file_location('source_worker_skill_store', Path(__file__).with_name('store.py'))
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)


def birth(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]


def update(db, ident, rid, **changes):
    source_status = changes.pop('sourceStatus', None)
    db.execute('BEGIN IMMEDIATE')
    try:
        job = api.sources.read_job(db, ident, rid, api)
        job.update(changes, updatedAt=api.now())
        source = api.sources.read(db, ident)
        if not source or source['revision'] != job['sourceRevision'] or source.get('lastRequestId') != rid:
            raise api.SkillFault('The original source binding is no longer active.', 409)
        db.execute('UPDATE skill_source_jobs SET metadata=? WHERE request_id=? AND skill_id=?', (api.encode(job), rid, ident))
        source.update(status=source_status or job['phase'], commit=job.get('commit'), updatedAt=job['updatedAt'])
        db.execute('UPDATE skill_sources SET metadata=? WHERE skill_id=?', (api.encode(source), ident))
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return job


def verify(path, repository, commit):
    fd = os.open(path / 'manifest.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 32 * 1024 * 1024:
            raise api.SkillFault('The source manifest exceeds its file or byte limit.', 503)
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024:
        raise api.SkillFault('The source manifest exceeds its byte limit.', 503)
    value = json.loads(raw)
    if value.get('schema') != 1 or value.get('repository') != repository or value.get('commit') != commit:
        raise api.SkillFault('The cached source identity differs.', 503)
    actual = set()
    root = api.folder(path / 'Repository')
    for item in value['files']:
        from source_checkout import relative
        relative(item['path'])
        file = root / item['path']
        if file.resolve(strict=True) != file:
            raise api.SkillFault('A source file is linked.', 503)
        info = file.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != item['bytes']:
            raise api.SkillFault('The downloaded source changed.', 503)
        with file.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
                raise api.SkillFault('The downloaded source hash differs.', 503)
        if bool(info.st_mode & 0o111) != item['executable'] or item['path'] in actual:
            raise api.SkillFault('The downloaded source manifest differs.', 503)
        actual.add(item['path'])
    found = set()
    for file in root.rglob('*'):
        info = file.lstat()
        if file.is_symlink() or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise api.SkillFault('The source cache contains a linked or special entry.', 503)
        if stat.S_ISREG(info.st_mode):
            found.add(file.relative_to(root).as_posix())
    if actual != found:
        raise api.SkillFault('The source cache inventory changed.', 503)
    return value, hashlib.sha256(raw).hexdigest()


def run(root, ident, rid):
    root = api.folder(root)
    if root.stat().st_uid != os.getuid():
        raise api.SkillFault('Run source jobs as the private skill owner.', 403)
    api.identity(ident)
    api.identity(rid)
    locks = api.folder(root / '.locks', True)
    fd = os.open(locks / ('source-' + rid), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as lock, api.lifecycle.lock(root, ident='lifetime-' + ident, fault=api.SkillFault):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        with closing(api.connect(root)) as db:
            api.detail(db, root, ident)
            job = api.sources.read_job(db, ident, rid, api)
            if job['phase'] != 'queued':
                return
            stage = None
            try:
                invocation = os.environ.get('STUDIO_SOURCE_INVOCATION') or os.environ.get('INVOCATION_ID')
                proof = dict(pid=os.getpid(), birth=birth(os.getpid()), release=str(Path(__file__).resolve().parents[2]),
                             invocationId=invocation, processEndConfirmed=False)
                update(db, ident, rid, phase='resolving', **proof)
                config = job['configuration']
                sources = api.folder(root / ident / 'Sources', True)
                stage = sources / ('.stage-' + rid)
                # An existing stage has an earlier original; preserve it for explicit reconciliation.
                stage.mkdir(mode=0o700)
                from source_checkout import Checkout
                def progress(**value):
                    update(db, ident, rid, **value)
                checkout = Checkout(stage, root.parent / 'GitHub', config.get('connectionId'), progress)
                commit, repository_id = checkout.resolve(config['repository'], config['ref'])
                update(db, ident, rid, phase='downloading', commit=commit, repositoryId=repository_id)
                destination = sources / commit
                if destination.exists() or destination.is_symlink():
                    manifest, manifest_hash = verify(api.folder(destination), config['repository'], commit)
                    shutil.rmtree(stage)
                    stage = None
                else:
                    content = checkout.materialize(config['repository'], commit)
                    manifest = dict(schema=1, repository=config['repository'], commit=commit, **content)
                    shutil.rmtree(stage / 'Git')  # The verified source snapshot has no credential or object-store dependency.
                    encoded = json.dumps(manifest, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n'
                    api.atomic(stage / 'manifest.json', encoded.encode('ascii'))
                    for directory, _, files in os.walk(stage / 'Repository', topdown=False):
                        for name in files:
                            with (Path(directory) / name).open('rb') as stream:
                                os.fsync(stream.fileno())
                        api.sync(Path(directory))
                    api.sync(stage)
                    os.rename(stage, destination)
                    api.sync(sources)
                    stage = None
                    manifest, manifest_hash = verify(destination, config['repository'], commit)
                result = dict(downloaded=True, published=False, commit=commit, manifestHash=manifest_hash,
                              sourcePath='Sources/' + commit, files=len(manifest['files']), bytes=manifest['totalBytes'],
                              repositories=manifest['repositories'],
                              externalLfsObjects=sum(bool(item.get('lfs')) for item in manifest['files']),
                              inertLinks=sum(bool(item.get('inertLink')) for item in manifest['files']))
                update(db, ident, rid, phase='complete', result=result, pid=None, sourceStatus='sources_ready')
            except Exception as error:
                # Fixed adapter diagnostics contain no credentials or upstream stderr.
                safe = str(error) if isinstance(error, api.SkillFault) or type(error).__name__ == 'ProjectFault' else 'The source job failed. Its original files were preserved for inspection.'
                try:
                    update(db, ident, rid, phase='failed', error=safe, pid=None)
                except Exception:
                    pass
                # Staging is retained on failure: a later lifecycle operation owns its cleanup.
                raise


if __name__ == '__main__':
    os.umask(0o077)
    try:
        if len(sys.argv) != 4:
            raise ValueError('Invalid source worker invocation.')
        run(Path(sys.argv[1]).absolute(), sys.argv[2], sys.argv[3])
    except Exception:
        sys.exit(1)
