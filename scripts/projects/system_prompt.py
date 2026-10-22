"""Global Studio instructions, outside all project workspaces and tool mounts."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

from store import ProjectFault

MAX_BYTES = 32768


def default_text():
    return json.loads((Path(__file__).resolve().parents[2] / 'shared/system-prompt.json').read_text())['text']


def validate_text(value):
    try:
        valid = (isinstance(value, str) and value.strip() and len(value.encode('utf-8')) <= MAX_BYTES
                 and not any((ord(c) < 32 and c not in '\t\n\r') or ord(c) == 127 for c in value))
    except UnicodeError:
        valid = False
    if not valid:
        raise ProjectFault('Enter a system prompt of at most 32 KiB without control characters.', 400)
    return value


def location(projects, create=False):
    root = Path(projects).absolute() / '.studio'
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.exists() or root.is_symlink():
        if root.resolve(strict=True) != root or not stat.S_ISDIR(root.lstat().st_mode):
            raise ProjectFault('System prompt storage is unavailable.', 503)
    path = root / 'Settings.sqlite'
    for candidate in (path, path.with_name(path.name + '-journal')):
        if candidate.exists() or candidate.is_symlink():
            if not stat.S_ISREG(candidate.lstat().st_mode):
                raise ProjectFault('System prompt storage is unavailable.', 503)
    return path


def value(prompt=None, revision=0):
    default = default_text()
    return {'text': default if prompt is None else validate_text(prompt), 'defaultText': default,
            'revision': revision, 'isDefault': prompt is None}


def row_value(db):
    if db.execute('PRAGMA user_version').fetchone()[0] != 1:
        raise ProjectFault('Unsupported system prompt storage.', 503)
    row = db.execute('SELECT prompt,revision FROM system_prompt WHERE id=1').fetchone()
    if row is None or type(row[1]) is not int or not 1 <= row[1] <= 9007199254740991:
        raise ProjectFault('System prompt storage is unavailable.', 503)
    return value(row[0], row[1])


def read(projects):
    path = location(projects)
    if not path.exists():
        return value()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        return row_value(db)


def snapshot(projects):
    current = read(projects)
    return {k: current[k] for k in ('text', 'revision')} | {'sha256': hashlib.sha256(current['text'].encode()).hexdigest()}


def update(projects, data, reset=False):
    expected = {'revision'} if reset else {'revision', 'text'}
    if not isinstance(data, dict) or set(data) != expected or type(data['revision']) is not int or not 0 <= data['revision'] < 9007199254740991:
        raise ProjectFault('Invalid system prompt settings.', 400)
    prompt = None if reset else validate_text(data['text'])
    if prompt == default_text(): prompt = None
    if not location(projects).exists() and data['revision'] != 0 and prompt is not None:
        raise ProjectFault('System prompt changed. Reload settings before saving.', 409)
    path = location(projects, create=True)
    with closing(sqlite3.connect(path, timeout=5)) as db:
        os.chmod(path, 0o600)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        schema = db.execute('PRAGMA user_version').fetchone()[0]
        if schema == 0:
            if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise ProjectFault('Unrecognized system prompt storage.', 503)
            db.execute('CREATE TABLE system_prompt (id INTEGER PRIMARY KEY CHECK(id=1), prompt TEXT, revision INTEGER NOT NULL)')
            db.execute('PRAGMA user_version=1')
            current = value()
        else:
            current = row_value(db)
        desired = value(prompt)
        # Identical retries are safe even when the first response was lost.
        if data['revision'] != current['revision'] and desired['text'] != current['text']:
            raise ProjectFault('System prompt changed. Reload settings before saving.', 409)
        if current['revision'] == 0 or desired['text'] != current['text'] or desired['isDefault'] != current['isDefault']:
            revision = current['revision'] + 1
            db.execute('INSERT INTO system_prompt VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET prompt=excluded.prompt,revision=excluded.revision', (prompt, revision))
        db.commit()
        return row_value(db)


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144: raise ProjectFault('System prompt request is too large.', 400)
    request = json.loads(raw)
    operation = request.get('operation')
    if request == {'operation': 'get'}:
        result = read(sys.argv[1])
    elif operation in ('save', 'reset') and set(request) == {'operation', 'input'}:
        result = update(sys.argv[1], request['input'], reset=operation == 'reset')
    else:
        raise ProjectFault('Invalid system prompt operation.', 400)
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'System prompt storage is unavailable. Existing data was preserved.', 'code': 503})); sys.exit(1)
