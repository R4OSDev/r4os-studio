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
from validation import fields
from reads import read
from mutations import mutate


def operation(projects, request):
    fields(request, ['operation', 'projectId'], ['requestId', 'input', 'target', 'collection', 'versionId', 'subversionId', 'cursor', 'limit'])
    name = request['operation']
    if name not in ('read', 'initialize', 'overview', 'list', 'get', 'notes', 'current', 'revision', 'mutate'):
        raise ProjectFault('Unsupported roadmap operation.', 400)
    if name in ('read', 'initialize'):
        fields(request, ['operation', 'projectId'], ['requestId'] if name == 'initialize' else [])
    elif name == 'mutate':
        fields(request, ['operation', 'projectId', 'input'])
    with connection(projects, request['projectId'], initialize=name == 'initialize') as db:
        if db is None:
            if name not in ('read', 'overview'):
                raise ProjectFault('Initialize this project roadmap before continuing.', 404)
            return {'exists': False, 'projectId': request['projectId']}
        if name == 'mutate':
            return mutate(db, request['projectId'], request['input'])
        if name == 'initialize' and 'requestId' in request:
            return mutate(db, request['projectId'], {'requestId': request['requestId']}, initialize=True)
        if name in ('read', 'initialize'):
            return {'exists': True, 'roadmap': snapshot(db)}
        return read(db, request['projectId'], request)


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
