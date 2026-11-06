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
from exports import chunk, open_archive, prepare


def _operation(projects, request):
    fields(request, ['operation', 'projectId'], ['requestId', 'input', 'target', 'collection', 'versionId', 'subversionId', 'cursor', 'limit', 'exportId', 'offset', 'workflowId'])
    name = request['operation']
    if name not in ('read', 'initialize', 'overview', 'list', 'get', 'notes', 'current', 'revision', 'mutate', 'export', 'export_info', 'export_chunk', 'workflows', 'workflow'):
        raise ProjectFault('Unsupported roadmap operation.', 400)
    if name in ('read', 'initialize'):
        fields(request, ['operation', 'projectId'], ['requestId'] if name == 'initialize' else [])
    elif name in ('mutate', 'export'):
        fields(request, ['operation', 'projectId', 'input'])
    with connection(projects, request['projectId'], initialize=name == 'initialize') as db:
        if db is None:
            if name == 'workflows':
                fields(request, ['operation', 'projectId'], ['versionId', 'limit', 'cursor'])
                if 'cursor' in request: raise ProjectFault('No workflow page exists in this project.', 404)
                return {'items': [], 'nextCursor': None}
            if name not in ('read', 'overview'):
                raise ProjectFault('Initialize this project roadmap before continuing.', 404)
            return {'exists': False, 'projectId': request['projectId']}
        if name == 'mutate':
            return mutate(db, request['projectId'], request['input'])
        if name in ('workflows', 'workflow'):
            from workflow_reads import read as read_workflows
            return read_workflows(db, request['projectId'], request)
        if name == 'export':
            return prepare(db, projects, request['projectId'], request['input'])
        if name == 'export_info':
            fields(request, ['operation', 'projectId', 'exportId'])
            with open_archive(projects, request['projectId'], request['exportId']) as (info, _):
                return info
        if name == 'export_chunk':
            return chunk(projects, request['projectId'], request)
        if name == 'initialize' and 'requestId' in request:
            return mutate(db, request['projectId'], {'requestId': request['requestId']}, initialize=True)
        if name in ('read', 'initialize'):
            return {'exists': True, 'roadmap': snapshot(db)}
        return read(db, request['projectId'], request)


def operation(projects,request,proof=None):
    if proof is None:return _operation(projects,request)
    # Only the fixed browser adapter opts into this private envelope. Agent,
    # export and direct callers keep their existing public result contract.
    from generation import capture
    before=capture(projects,request['projectId'])
    result=_operation(projects,request)
    after=capture(projects,request['projectId'])
    binding=result.get('roadmap') if isinstance(result,dict) and result.get('exists') else result
    if before is not None and before==after and isinstance(binding,dict) and type(binding.get('revision')) is int and isinstance(binding.get('currentVersionId'),str):
        proof.update({'projectId':request['projectId'],'binding':{key:binding[key] for key in ('revision','currentVersionId')},'files':after})
    return result


def revision_probe(projects,request):
    fields(request,['operation','projectId'])
    if request['operation']!='revision':raise ProjectFault('Only revision reads support a verified probe.',400)
    # The fixed browser parent admits this probe only against its matching
    # fully verified generation, checks that generation again after close,
    # and keeps the original project lifetime/schema/owner/SQLite read gates.
    with connection(projects,request['projectId'],verify_integrity=False) as db:
        if db is None:raise ProjectFault('Initialize this project roadmap before continuing.',404)
        return read(db,request['projectId'],request)


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072:
        raise ProjectFault('Roadmap request is too large.', 413)
    proof={} if len(sys.argv)==3 and sys.argv[2]=='--verified-read' else None
    request=json.loads(raw)
    result = revision_probe(Path(sys.argv[1]),request) if len(sys.argv)==3 and sys.argv[2]=='--revision-probe' else operation(Path(sys.argv[1]),request,proof)
    print(json.dumps({'result': result,**({'generation':proof} if proof else {})}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Roadmap storage is unavailable. Existing data was preserved.', 'code': 503}))
        sys.exit(1)
