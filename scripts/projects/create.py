"""Recoverable project publication. Only trusted SDK/template tools are executed."""
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid
from store import connect, public, check_vm, ProjectFault
from sdk import profile, TYPES
from templates import render, hashes, revision as template_revision


def validate_input(data):
    template = next((value for value in TYPES if value[0] == data['template']), None)
    if not template or data['language'] not in ('Rust', 'Zig', 'C'):
        raise ProjectFault('This language and module type are not supported.', 400)
    if (data['template'] == 'subsystem') != bool(data.get('guestFormats')):
        raise ProjectFault('Guest formats are required only for a subsystem host.', 400)
    if data['template'] == 'subsystem' and (len(data['name'].encode()) > 96 or any(c in data['name'] for c in ('"', '\\'))):
        raise ProjectFault('Subsystem names allow up to 96 UTF-8 bytes and cannot contain quotes or backslashes.', 400)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(path):
    for item in path.rglob('*'):
        if item.is_symlink():
            raise ProjectFault('Unexpected project files. The staging data was preserved.')
        if item.is_file():
            fd = os.open(item, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    for folder in sorted([p for p in path.rglob('*') if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
        sync_directory(folder)
    sync_directory(path)
    sync_directory(path.parent)


def publish(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
        raise OSError(ctypes.get_errno(), 'Project publication failed.')
    sync_directory(source.parent)
    sync_directory(target.parent)


def finish(db, projects, root, request):
    project = public(db.execute('SELECT * FROM projects WHERE id=?', (request['project_id'],)).fetchone())
    if not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', project['id']):
        raise ProjectFault('Invalid project journal identity. All files were preserved.')
    if request['phase'] == 'complete':
        return project
    document = json.loads(request['hashes'])
    stage = projects / '.studio/staging' / project['id']
    target = projects / project['id']
    if request['phase'] == 'reserved':
        if stage.exists() or stage.is_symlink():
            if stage.is_symlink():
                raise ProjectFault('Unexpected staging data. It was preserved.')
            # Retain interrupted, not yet verified contents; never delete unknown edits.
            preserved = stage.with_name(stage.name + '.interrupted.' + str(uuid.uuid4()))
            publish(stage, preserved)
        context = profile(root, projects, project['pins'])
        if document.get('templateRevision', document['input']['optionsRevision']) != context['templateRevision']:
            raise ProjectFault('The saved template revision is unavailable. All pending files were preserved.')
        stage.mkdir(mode=0o700, parents=True)
        source = stage / 'Workspace' if document.get('layout', 1) == 2 else stage
        render(context, source, {**document['input'], 'id': project['id'], 'moduleName': project['moduleName']})
        sync_tree(stage)
        document['files'] = hashes(stage)
        with db:
            db.execute("UPDATE requests SET phase='prepared',hashes=?,error=NULL WHERE request_key=?",
                       (json.dumps(document), request['request_key']))
    expected = document.get('files')
    if not expected:
        raise ProjectFault('The project journal requires review. All files were preserved.')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or hashes(target) != expected:
            raise ProjectFault('The project directory changed. All files were preserved.')
    else:
        if stage.is_symlink() or hashes(stage) != expected:
            raise ProjectFault('The staged project changed. All files were preserved.')
        check_vm(root, project['vmId'])
        publish(stage, target)
    with db:
        db.execute("UPDATE projects SET state='ready' WHERE id=?", (project['id'],))
        db.execute("UPDATE requests SET phase='complete',error=NULL WHERE request_key=?", (request['request_key'],))
    return public(db.execute('SELECT * FROM projects WHERE id=?', (project['id'],)).fetchone())


def create(db, projects, root, data):
    request_key = data['requestId']
    encoded = json.dumps({k: v for k, v in data.items() if k != 'requestId'}, sort_keys=True, separators=(',', ':'))
    request_hash = hashlib.sha256(encoded.encode()).hexdigest()
    retired = db.execute('SELECT request_hash FROM retired_project_requests WHERE request_key=?', (request_key,)).fetchone()
    if retired:
        if retired['request_hash'] != request_hash: raise ProjectFault('This request ID belongs to another submission.')
        raise ProjectFault('This project was deleted. Start a new project request.', 410)
    old = db.execute('SELECT * FROM requests WHERE request_key=?', (request_key,)).fetchone()
    if old:
        if db.execute('SELECT 1 FROM project_deletions WHERE project_id=?', (old['project_id'],)).fetchone():
            raise ProjectFault('This project is being deleted.', 409)
        if old['request_hash'] != request_hash:
            raise ProjectFault('This request ID belongs to a different project submission.')
        return finish(db, projects, root, old)
    validate_input(data)
    context = profile(root, projects)
    if data['optionsRevision'] != context['revision']:
        raise ProjectFault('Project options changed. Reload the available options.')
    from toolset import combination
    template = next(value for value in TYPES if value[0] == data['template'])
    match = combination(context, template, data['language'])
    if not match or not match['supported']:
        raise ProjectFault(match['reason'] if match else 'The SDK template is unavailable.', 400)
    if data['language'] == 'Rust':
        if not context.get('rust'): raise ProjectFault(context.get('rustError', 'Rust tools are unavailable.'), 400)
        context['pins']['rust'] = context['rust']['pin']
        context['templateRevision'] = template_revision(context['pins'])
    check_vm(root, data['vmId'])
    identity = str(uuid.uuid4())
    prefix = re.sub('[^A-Z0-9]', '', data['name'].upper())[:16] or 'PROJECT'
    if not prefix[0].isalpha():
        prefix = 'P' + prefix[:15]
    module_name = prefix + '_' + identity.replace('-', '')[:8].upper()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db:
        db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,1,'pending')",
                   (identity, data['name'], data['description'], data['language'], data['template'], module_name,
                    data['vmId'], json.dumps(context['pins']), now, now))
        db.execute("INSERT INTO requests VALUES (?,?,?,'reserved',?,NULL)",
                   (request_key, request_hash, identity, json.dumps({'input': data, 'templateRevision': context['templateRevision'], 'layout': 2})))
    request = db.execute('SELECT * FROM requests WHERE request_key=?', (request_key,)).fetchone()
    return finish(db, projects, root, request)


def main():
    os.umask(0o077)
    data = sys.stdin.buffer.read(131073)
    if len(data) > 131072:
        raise ProjectFault('The project request is too large.', 400)
    request = json.loads(data)
    projects = Path(sys.argv[1]).absolute()
    root = Path(sys.argv[2]).resolve()
    with connect(projects) as db:
        for directory in (projects / '.studio', projects / '.studio/staging'):
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.resolve(strict=True) != directory.absolute():
                raise ProjectFault('Invalid project working directory.')
        with (projects / '.studio/create.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if request['operation'] == 'create':
                result = create(db, projects, root, request['input'])
            elif request['operation'] == 'recover':
                result = []
                for item in db.execute("SELECT r.* FROM requests r JOIN projects p ON p.id=r.project_id WHERE p.state='pending'").fetchall():
                    try:
                        finish(db, projects, root, item)
                        result.append({'id': item['project_id'], 'recovered': True})
                    except Exception:
                        result.append({'id': item['project_id'], 'recovered': False})
                        with db:
                            db.execute('UPDATE requests SET error=? WHERE request_key=?',
                                       ('Project creation is incomplete. Retry the original request.', item['request_key']))
            else:
                raise ProjectFault('Unsupported creation operation.', 400)
    print(json.dumps({'result': result}))


if __name__ == '__main__':
    try:
        main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code}))
        sys.exit(1)
    except Exception as error:
        print(str(error), file=sys.stderr)
        print(json.dumps({'error': 'Project creation could not be completed. Retry this request.', 'code': 503}))
        sys.exit(1)
