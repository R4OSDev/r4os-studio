"""Private global skill drafts and immutable snapshots. Fixed bounded JSON RPC."""
import base64
from contextlib import closing, contextmanager
import datetime
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import uuid

spec_lifecycle=importlib.util.spec_from_file_location('studio_skill_lifecycle',Path(__file__).with_name('lifecycle.py'))
lifecycle=importlib.util.module_from_spec(spec_lifecycle);spec_lifecycle.loader.exec_module(lifecycle)

MAX_FILE = 1024 * 1024
MAX_TOTAL = 8 * MAX_FILE
MAX_FILES = 128


class SkillFault(Exception):
    def __init__(self, message, code=409):
        super().__init__(message)
        self.code = code


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def encode(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
def digest(data): return hashlib.sha256(data).hexdigest()


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise SkillFault('Invalid skill identity.', 400)
    return value


def folder(path, create=False):
    path = Path(path).absolute()
    if create: path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.resolve(strict=True) != path or not stat.S_ISDIR(path.lstat().st_mode):
        raise SkillFault('Linked skill directories are not supported. Existing data was preserved.', 503)
    return path


def relative(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 240:
        raise SkillFault('Invalid skill file path.', 400)
    p = PurePosixPath(value)
    if str(p) != value or p.is_absolute() or any(not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_. -]{0,79}', part) or part in ('.', '..') for part in p.parts):
        raise SkillFault('Use bounded relative package paths without traversal or hidden directories.', 400)
    if value != 'SKILL.md' and (len(p.parts) < 2 or p.parts[0] not in ('scripts', 'references', 'assets', 'agents')):
        raise SkillFault('Use SKILL.md or a file under scripts/, references/, assets/ or agents/.', 400)
    return p


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def atomic(path, data, executable=False):
    temporary = path.with_name('.write-' + str(uuid.uuid4()))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700 if executable else 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); sync(path.parent)
    finally:
        if temporary.exists(): temporary.unlink()


def regular(path):
    try: fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError: raise SkillFault('Skill file not found.', 404) from None
    except OSError as error:
        if error.errno == errno.ELOOP: raise SkillFault('Linked skill files are not supported.', 400) from None
        raise
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_FILE:
            raise SkillFault('Skill packages require regular unlinked files up to 1 MiB.', 400)
        data = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
        if len(data) > MAX_FILE or (info.st_size, info.st_mtime_ns, info.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise SkillFault('A skill file changed while reading. Retry.', 409)
        return data, bool(info.st_mode & 0o111)


def inventory(workspace):
    files = []; contents = {}; normalized = set(); total = 0; entries = 0
    for parent, directories, names in os.walk(folder(workspace), followlinks=False):
        entries += len(directories) + len(names)
        if entries > 512: raise SkillFault('Skill package has too many directory entries.', 400)
        for name in directories:
            folder(Path(parent) / name)
            relative(str((Path(parent) / name).relative_to(workspace)) + '/placeholder')
        for name in sorted(names):
            path = Path(parent) / name
            rel = str(path.relative_to(workspace)); relative(rel)
            if rel.casefold() in normalized: raise SkillFault('Skill paths must be unique ignoring case.', 400)
            normalized.add(rel.casefold())
            data, executable = regular(path)
            if rel == 'SKILL.md' and len(data) > 65536: raise SkillFault('SKILL.md exceeds 64 KiB.', 400)
            total += len(data)
            if len(files) >= MAX_FILES or total > MAX_TOTAL: raise SkillFault('Skill package exceeds 128 files or 8 MiB.', 400)
            files.append({'path': rel, 'sha256': digest(data), 'bytes': len(data), 'executable': executable})
            contents[rel] = data
    files.sort(key=lambda f: f['path'])
    return files, contents, digest(encode(files).encode())


def validate(files, contents, tree_hash, node):
    if 'SKILL.md' not in contents: return {'valid': False, 'errors': ['SKILL.md is required.'], 'draftHash': tree_hash}
    completed = subprocess.run([node, str(Path(__file__).with_name('validate.mjs'))], input=contents['SKILL.md'],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5,
                               env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    result = json.loads(completed.stdout)
    if completed.returncode or not isinstance(result, dict): raise SkillFault('Skill validation is unavailable.', 503)
    errors = ['SKILL.md: ' + message for message in result['errors']]
    # Local Markdown resource links must stay in this complete package. URLs are informational only.
    try: text = contents['SKILL.md'].decode('utf-8', errors='strict')
    except UnicodeError: text = ''; errors.append('SKILL.md must be valid UTF-8 text.')
    for target in re.findall(r'\]\(([^\s)]+)(?:\s+[^)]*)?\)', text):
        target = target.split('#', 1)[0]
        if not target or target.startswith(('https://', 'http://', 'mailto:')): continue
        try:
            relative(target)
            if target not in contents: errors.append('SKILL.md: linked resource ' + target + ' is missing from the package.')
        except SkillFault: errors.append('SKILL.md: a linked local resource is outside the allowed package paths.')
    for f in files:
        if not f['path'].startswith('assets/'):
            try:
                value = contents[f['path']].decode('utf-8')
                if '\x00' in value: raise UnicodeError()
            except UnicodeError: errors.append(f['path'] + ': use UTF-8 text without NUL characters.')
    return {**result, 'valid': not errors, 'errors': errors[:20], 'draftHash': tree_hash}


def connect(root):
    folder(root, True)
    path = root / 'Skills.sqlite'
    for candidate in (path, root / 'Skills.sqlite-journal', root / 'Skills.sqlite-wal', root / 'Skills.sqlite-shm'):
        if candidate.exists() or candidate.is_symlink():
            if not stat.S_ISREG(candidate.lstat().st_mode): raise SkillFault('Invalid skill catalog. Existing data was preserved.', 503)
    db = sqlite3.connect(path, timeout=5); db.row_factory = sqlite3.Row
    os.chmod(path, 0o600); db.execute('PRAGMA synchronous=FULL'); db.execute('PRAGMA foreign_keys=ON')
    db.execute('BEGIN IMMEDIATE')
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 0:
        if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone(): raise SkillFault('Unrecognized skill catalog.', 503)
        db.execute('''CREATE TABLE skills(id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,
            format_name TEXT, description TEXT NOT NULL, active_revision INTEGER NOT NULL, active_hash TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, state TEXT NOT NULL)''')
        db.execute('''CREATE TABLE revisions(skill_id TEXT NOT NULL REFERENCES skills(id), number INTEGER NOT NULL,
            hash TEXT NOT NULL, metadata TEXT NOT NULL, PRIMARY KEY(skill_id,number))''')
        db.execute('''CREATE TABLE saves(request_id TEXT PRIMARY KEY, skill_id TEXT NOT NULL REFERENCES skills(id),
            request_hash TEXT NOT NULL, result TEXT NOT NULL)''')
        db.execute('PRAGMA user_version=1')
    elif version != 1: raise SkillFault('Unsupported skill catalog. Existing data was preserved.', 503)
    db.commit()
    return db


def summary(row):
    if row is None: raise SkillFault('Skill not found.', 404)
    return {'id': row['id'], 'name': row['name'], 'revision': row['revision'], 'formatName': row['format_name'],
            'description': row['description'], 'activeRevision': row['active_revision'], 'activeHash': row['active_hash'],
            'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


@contextmanager
def author_locked(root, ident, author=None):
    identity(ident)
    if author is not None:
        author.verify(root, ident)
        yield
        return
    locks = folder(root / '.locks', True)
    fd = os.open(locks / ident, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): raise SkillFault('Invalid skill lock.', 503)
        try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise SkillFault('This skill is being edited. Retry after the active operation.', 409) from None
        sessions = root / ident / 'Sessions/Sessions.sqlite'
        if sessions.exists() or sessions.is_symlink():
            if sessions.resolve(strict=True) != sessions or not stat.S_ISREG(sessions.stat().st_mode):
                raise SkillFault('Skill session storage is unavailable. Existing data was preserved.', 503)
            with closing(sqlite3.connect(sessions.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('SELECT 1 FROM runs WHERE busy=1 LIMIT 1').fetchone():
                    raise SkillFault('Stop or finish the active Skill Manager run before editing this draft.', 409)
        yield


@contextmanager
def locked(root, ident, author=None):
    with lifecycle.lock(root,fault=SkillFault):
        with author_locked(root,ident,author):yield

def detail(db, root, ident):
    if lifecycle.deleted(root,ident):raise SkillFault('Skill was deleted.',404)
    row = db.execute("SELECT * FROM skills WHERE id=? AND state='ready'", (ident,)).fetchone()
    value = summary(row)
    files, _, tree_hash = inventory(folder(root / ident) / 'Workspace')
    return {'skill': value, 'files': files, 'draftHash': tree_hash}


def create(db, root, data):
    if set(data) != {'id', 'name'}: raise SkillFault('Unexpected skill fields.', 400)
    ident = identity(data['id']); name = data['name']
    if lifecycle.deleted(root,ident):raise SkillFault('This skill identity was deleted. Create a new skill explicitly.',409)
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in name):
        raise SkillFault('Enter a skill display name of at most 120 characters.', 400)
    with locked(root, ident):
        row = db.execute('SELECT * FROM skills WHERE id=?', (ident,)).fetchone()
        if row and row['name'] != name.strip(): raise SkillFault('This skill ID is already in use.', 409)
        if row is None:
            if (root / ident).exists() or (root / ident).is_symlink(): raise SkillFault('The skill folder already exists. Data was preserved.', 409)
            db.execute('BEGIN IMMEDIATE'); stamp = now()
            if db.execute('SELECT COUNT(*) FROM skills').fetchone()[0] >= 256: raise SkillFault('The skill limit of 256 has been reached.', 409)
            db.execute("INSERT INTO skills VALUES(?,?,1,NULL,'',0,NULL,?,?,'creating')", (ident, name.strip(), stamp, stamp)); db.commit()
        if row is None or row['state'] == 'creating':
            owner = folder(root / ident, True)
            for sub in ('Workspace', 'Revisions', 'Sessions'): folder(owner / sub, True)
            path = owner / 'Workspace/SKILL.md'
            if not path.exists(): atomic(path, b'---\nname: new-skill\ndescription: ""\n---\n\n')
            db.execute("UPDATE skills SET state='ready' WHERE id=?", (ident,)); db.commit()
        return detail(db, root, ident)


def file_path(root, ident, value, create_parents=False):
    path = folder(folder(root / identity(ident)) / 'Workspace')
    rel = relative(value)
    for segment in rel.parts[:-1]: path = folder(path / segment, create_parents)
    return path / rel.name


def expected_file(path, expected):
    if expected is not None and (not isinstance(expected, str) or not re.fullmatch('[a-f0-9]{64}', expected)):
        raise SkillFault('Invalid file revision.', 400)
    if path.exists() or path.is_symlink():
        data, _ = regular(path)
        if digest(data) != expected: raise SkillFault('This skill file changed. Reload before editing.', 409)
    elif expected is not None: raise SkillFault('This skill file no longer exists.', 409)


def write_file(db, root, data):
    if set(data) != {'id', 'path', 'sha256', 'content', 'encoding', 'executable'}: raise SkillFault('Unexpected file fields.', 400)
    ident = identity(data['id']); relative(data['path'])
    if type(data['executable']) is not bool or not isinstance(data['content'], str): raise SkillFault('Invalid skill file.', 400)
    try:
        if data['encoding'] == 'utf8': content = data['content'].encode('utf-8')
        elif data['encoding'] == 'base64' and data['path'].startswith('assets/'): content = base64.b64decode(data['content'], validate=True)
        else: raise ValueError()
    except (ValueError, UnicodeError): raise SkillFault('Use UTF-8 text, or base64 for binary assets.', 400) from None
    if len(content) > MAX_FILE or (data['path'] == 'SKILL.md' and len(content) > 65536): raise SkillFault('Skill file is too large.', 400)
    with locked(root, ident):
        current = detail(db, root, ident)
        path = file_path(root, ident, data['path'], True); expected_file(path, data['sha256'])
        previous = next((f for f in current['files'] if f['path'] == data['path']), None)
        if not previous and len(current['files']) >= MAX_FILES: raise SkillFault('Skill has too many files.', 400)
        if sum(f['bytes'] for f in current['files']) - (previous['bytes'] if previous else 0) + len(content) > MAX_TOTAL: raise SkillFault('Skill exceeds 8 MiB.', 400)
        if any(f['path'].casefold() == data['path'].casefold() and f['path'] != data['path'] for f in current['files']): raise SkillFault('Skill paths must be unique ignoring case.', 400)
        atomic(path, content, data['executable'])
        return detail(db, root, ident)


def rename_skill(db, root, data):
    if set(data) != {'id', 'revision', 'name'} or type(data['revision']) is not int or not isinstance(data['name'], str) or not data['name'].strip() or len(data['name']) > 120 or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in data['name']):
        raise SkillFault('Invalid skill display name or revision.', 400)
    ident = identity(data['id']); name = data['name'].strip()
    with locked(root, ident):
        current = detail(db, root, ident)['skill']
        if current['revision'] != data['revision'] and current['name'] != name: raise SkillFault('This skill changed. Reload before renaming.', 409)
        if current['name'] != name:
            db.execute('UPDATE skills SET name=?,revision=revision+1,updated_at=? WHERE id=?', (name, now(), ident)); db.commit()
        return detail(db, root, ident)


def change_file(db, root, data, rename=False):
    fields = {'id', 'path', 'sha256', 'destination'} if rename else {'id', 'path', 'sha256'}
    if set(data) != fields or data['sha256'] is None: raise SkillFault('Invalid skill file change.', 400)
    ident = identity(data['id'])
    with locked(root, ident):
        detail(db, root, ident)
        source = file_path(root, ident, data['path']); expected_file(source, data['sha256'])
        if rename:
            target = file_path(root, ident, data['destination'], True)
            if target == source: return detail(db, root, ident)
            if target.exists() or target.is_symlink(): raise SkillFault('Destination already exists.', 409)
            current = detail(db, root, ident)
            if any(f['path'] != data['path'] and f['path'].casefold() == data['destination'].casefold() for f in current['files']): raise SkillFault('Destination conflicts ignoring case.', 409)
            os.rename(source, target); sync(target.parent)
        else: source.unlink()
        sync(source.parent)
        return detail(db, root, ident)


def publish(db, root, data, node, author=None):
    if set(data) != {'id', 'revision', 'draftHash', 'requestId'} or type(data['revision']) is not int or data['revision'] < 1 or not isinstance(data['draftHash'], str) or not re.fullmatch('[a-f0-9]{64}', data['draftHash']):
        raise SkillFault('Invalid skill save request.', 400)
    ident = identity(data['id']); identity(data['requestId']); request_hash = digest(encode(data).encode())
    with locked(root, ident, author):
        previous = db.execute('SELECT * FROM saves WHERE request_id=?', (data['requestId'],)).fetchone()
        if previous:
            if previous['request_hash'] != request_hash: raise SkillFault('This save ID has already been used.', 409)
            return json.loads(previous['result'])
        current = detail(db, root, ident)
        files, contents, tree_hash = inventory(root / ident / 'Workspace')
        if current['skill']['revision'] != data['revision'] or tree_hash != data['draftHash']: raise SkillFault('This skill changed. Reload before saving.', 409)
        validation = validate(files, contents, tree_hash, node)
        if not validation['valid']: return {**current, 'validation': validation, 'saved': False}
        revisions = folder(root / ident / 'Revisions'); destination = revisions / tree_hash
        if not destination.exists():
            stage = revisions / ('.stage-' + str(uuid.uuid4()))
            try:
                workspace = folder(stage / 'Workspace', True)
                for f in files:
                    path = workspace / f['path']; folder(path.parent, True); atomic(path, contents[f['path']], f['executable'])
                atomic(stage / 'revision.json', (encode({'files': files, 'hash': tree_hash, 'metadata': validation['metadata']}) + '\n').encode())
                for directory, _, _ in os.walk(workspace, topdown=False): sync(directory)
                sync(stage)
                if author is not None: author.verify(root, ident)
                os.rename(stage, destination); sync(revisions)
            finally:
                if stage.exists(): shutil.rmtree(stage)
        actual, _, actual_hash = inventory(folder(destination) / 'Workspace')
        if actual != files or actual_hash != tree_hash: raise SkillFault('The immutable skill snapshot changed. Data was preserved.', 503)
        if inventory(root / ident / 'Workspace')[2] != tree_hash: raise SkillFault('The skill changed during validation. Retry with the current draft.', 409)
        if author is not None: author.verify(root, ident)
        db.execute('BEGIN IMMEDIATE')
        active = current['skill']['activeRevision']
        if current['skill']['activeHash'] != tree_hash:
            active += 1
            db.execute('INSERT INTO revisions VALUES(?,?,?,?)', (ident, active, tree_hash, encode(validation['metadata'])))
            db.execute('UPDATE skills SET revision=revision+1,format_name=?,description=?,active_revision=?,active_hash=?,updated_at=? WHERE id=?',
                       (validation['metadata']['name'], validation['metadata']['description'], active, tree_hash, now(), ident))
        result = {**detail(db, root, ident), 'validation': validation, 'saved': True}
        db.execute('INSERT INTO saves VALUES(?,?,?,?)', (data['requestId'], ident, request_hash, encode(result)))
        db.commit(); return result


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(16 * MAX_FILE + 1)
    if len(raw) > 16 * MAX_FILE: raise SkillFault('Skill request is too large.', 400)
    request = json.loads(raw); root = Path(sys.argv[1]).absolute(); node = sys.argv[2]
    if not isinstance(request, dict): raise SkillFault('Invalid skill request.', 400)
    operation = request.get('operation')
    with closing(connect(root)) as db:
        if operation == 'ensure_builtin' and set(request) == {'operation'}:
            from builtin import ensure
            result=ensure(db,root,node,sys.modules[__name__])
        elif operation == 'list' and set(request) == {'operation'}:
            result = [summary(row) for row in db.execute("SELECT * FROM skills WHERE state='ready' ORDER BY created_at,id") if not lifecycle.deleted(root,row['id'])]
        elif operation == 'create' and set(request) == {'operation', 'input'}: result = create(db, root, request['input'])
        elif operation in ('get', 'validate') and set(request) == {'operation', 'id'}:
            ident = identity(request['id']); result = detail(db, root, ident)
            if operation == 'validate':
                with locked(root, ident):
                    files, contents, tree_hash = inventory(root / ident / 'Workspace'); result = validate(files, contents, tree_hash, node)
        elif operation == 'write' and set(request) == {'operation', 'input'}: result = write_file(db, root, request['input'])
        elif operation == 'rename' and set(request) == {'operation', 'input'}: result = rename_skill(db, root, request['input'])
        elif operation in ('remove_file', 'rename_file') and set(request) == {'operation', 'input'}: result = change_file(db, root, request['input'], operation == 'rename_file')
        elif operation == 'save' and set(request) == {'operation', 'input'}: result = publish(db, root, request['input'], node)
        elif operation == 'read' and set(request) == {'operation', 'id', 'path'}:
            ident = identity(request['id']); detail(db, root, ident)
            path = file_path(root, ident, request['path']); data, executable = regular(path)
            try:
                content = data.decode('utf-8')
                if '\x00' in content: raise UnicodeError()
                encoding = 'utf8'
            except UnicodeError: content = base64.b64encode(data).decode('ascii'); encoding = 'base64'
            result = {'path': request['path'], 'sha256': digest(data), 'bytes': len(data), 'executable': executable, 'encoding': encoding, 'content': content}
        else: raise SkillFault('Invalid skill operation.', 400)
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except SkillFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Skill storage is unavailable. Existing data was preserved.', 'code': 503})); sys.exit(1)
