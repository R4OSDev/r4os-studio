"""One bounded project instruction file. No native directory discovery."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
from store import ProjectFault
from layout import workspace, sync
from project_use import acquire
from project_maintenance import project, busy, require_idle

NAME = 'Agents.md'
MAX_BYTES = 32768


def validate(text):
    try:
        valid = isinstance(text, str) and len(text.encode('utf-8')) <= MAX_BYTES and not any(
            (ord(c) < 32 and c not in '\t\n\r') or ord(c) == 127 for c in text)
    except UnicodeError: valid = False
    if not valid: raise ProjectFault('Enter at most 32 KiB of UTF-8 text without control characters.', 400)
    return text


def initial(value):
    return validate('Titel: ' + value['name'] + '\nBeschreibung: ' + value['description'] + '\n')


def read_at(directory, value):
    directory = Path(directory).absolute()
    if directory.resolve(strict=True) != directory: raise ProjectFault('Invalid project instruction directory.', 409)
    if any(p.name.casefold() == NAME.casefold() and p.name != NAME for p in directory.iterdir()):
        raise ProjectFault('Conflicting Agents.md filename. Preserve and resolve the existing file first.', 409)
    path = directory / NAME
    try: descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {'path': NAME, 'text': initial(value), 'sha256': None, 'exists': False}
    except OSError: raise ProjectFault('Agents.md is unavailable. Its contents were preserved.', 409) from None
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
            raise ProjectFault('Agents.md must be a regular file of at most 32 KiB.', 409)
        raw = stream.read(MAX_BYTES + 1); after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ProjectFault('Agents.md changed while being read. Retry the request.', 409)
    try: text = validate(raw.decode('utf-8'))
    except UnicodeError: raise ProjectFault('Agents.md must contain valid UTF-8. Its contents were preserved.', 409) from None
    return {'path': NAME, 'text': text, 'sha256': hashlib.sha256(raw).hexdigest(), 'exists': True}


def write_at(directory, value, text, expected):
    text = validate(text); current = read_at(directory, value)
    if current['exists'] and current['text'] == text: return current
    if current['sha256'] != expected:
        raise ProjectFault('Agents.md changed. Reload it before saving.', 409)
    path = Path(directory) / NAME; temporary = path.with_name('.Agents.' + uuid.uuid4().hex + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(text.encode('utf-8')); stream.flush(); os.fsync(stream.fileno())
        if read_at(directory, value)['sha256'] != expected:
            raise ProjectFault('Agents.md changed. Reload it before saving.', 409)
        if current['exists']: os.replace(temporary, path)
        else:
            try: os.link(temporary, path, follow_symlinks=False)
            except FileExistsError: raise ProjectFault('Agents.md was created concurrently. Reload before saving.', 409) from None
            temporary.unlink()
        sync(path.parent)
    finally: temporary.unlink(missing_ok=True)
    return read_at(directory, value)


def ensure_at(directory, value):
    current = read_at(directory, value)
    if current['exists']: return current
    return write_at(directory, value, current['text'], None)


def snapshot(projects, identity, value):
    current = ensure_at(workspace(projects, identity, True), value)
    return {k: current[k] for k in ('path', 'text', 'sha256')}


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144: raise ProjectFault('Project instructions request is too large.', 400)
    request = json.loads(raw); operation = request.get('operation')
    if operation not in ('get', 'save') or set(request) != ({'operation', 'id'} | ({'input'} if operation == 'save' else set())):
        raise ProjectFault('Invalid project instructions request.', 400)
    projects, identity = Path(sys.argv[1]).absolute(), request['id']
    with acquire(projects, identity, exclusive=operation == 'save'):
        value = project(projects, identity); directory = workspace(projects, identity, True)
        if operation == 'get': result = {**read_at(directory, value), 'editable': not busy(projects, identity)}
        else:
            require_idle(projects, identity); data = request['input']
            if (not isinstance(data, dict) or set(data) != {'text', 'sha256'} or
                (data['sha256'] is not None and (not isinstance(data['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', data['sha256'])))):
                raise ProjectFault('Invalid project instructions fields.', 400)
            result = {**write_at(directory, value, data['text'], data['sha256']), 'editable': True}
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Project instructions are unavailable. Existing data was preserved.', 'code': 503})); sys.exit(1)
