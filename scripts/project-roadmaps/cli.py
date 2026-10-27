#!/usr/bin/env python3
"""Fixed unprivileged JSON adapter. Never accepts filesystem paths in input."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'projects'))
from store import ProjectFault
from storage import connection
from model import snapshot


def operation(projects, request):
    if (not isinstance(request, dict) or set(request) != {'operation', 'projectId'}
            or request['operation'] not in ('read', 'initialize')):
        raise ProjectFault('Unsupported roadmap operation.', 400)
    with connection(projects, request['projectId'], initialize=request['operation'] == 'initialize') as db:
        return {'exists': True, 'roadmap': snapshot(db)} if db else {'exists': False, 'projectId': request['projectId']}


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072:
        raise ProjectFault('Roadmap request is too large.', 413)
    result = operation(Path(sys.argv[1]), json.loads(raw))
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Roadmap storage is unavailable. Existing data was preserved.', 'code': 503}))
        sys.exit(1)
