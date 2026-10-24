"""Fixed project editor operations for the existing unprivileged web service."""
import json
import os
from pathlib import Path
import sys
from editor_files import root_path, node, tree, MAX_TEXT, MAX_OPEN
from project_use import acquire, project_id
from project_maintenance import busy
from store import ProjectFault


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024: raise ProjectFault('Editor request is too large.', 413)
    request = json.loads(raw)
    if not isinstance(request, dict) or set(request) - {'operation', 'id', 'input', 'hosts'} or not {'operation', 'id', 'input'} <= set(request) or not isinstance(request['input'], dict):
        raise ProjectFault('Invalid editor request.', 400)
    operation, data = request['operation'], request['input']
    projects, identity = Path(sys.argv[1]).absolute(), project_id(request['id'])
    if operation == 'mutation':
        from editor_mutations import mutate
        print(json.dumps({'result': mutate(projects, identity, data, request.get('hosts'))})); return
    with acquire(projects, identity):
        path = root_path(projects, identity)
        root = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if operation == 'tree' and set(data) <= {'path', 'offset', 'revision'}:
                offset = data.get('offset', 0)
                if type(offset) is not int or not 0 <= offset <= 10000: raise ProjectFault('Invalid directory page.', 400)
                result = tree(root, data.get('path', ''), offset, data.get('revision'))
            elif operation == 'file' and set(data) == {'path'}:
                result = node(root, data['path'], content=True)
            elif operation == 'status' and set(data) == {'paths'}:
                if not isinstance(data['paths'], list) or len(data['paths']) > MAX_OPEN: raise ProjectFault('Too many open files.', 400)
                active = busy(projects, identity)
                result = {'writable': not active, 'reason': 'Wait for active runs and development jobs to finish.' if active else None,
                          'busy': active, 'maxTextBytes': MAX_TEXT, 'mutations': 1,
                          'files': [node(root, relative) for relative in data['paths']]}
            elif operation == 'receipt' and set(data) == {'requestId'}:
                from editor_mutations import receipt
                result = receipt(projects, identity, data['requestId'])
            else: raise ProjectFault('Unsupported editor operation.', 400)
            current = path.stat()
            opened = os.fstat(root)
            if path.resolve(strict=True) != path or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ProjectFault('The Workspace changed. Reopen the editor.', 409)
        finally: os.close(root)
    print(json.dumps({'result': result}, ensure_ascii=True))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except FileNotFoundError:
        print(json.dumps({'error': 'The Workspace path no longer exists. Refresh it.', 'code': 404})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Editor access is unavailable. Existing files were preserved.', 'code': 409})); sys.exit(1)
