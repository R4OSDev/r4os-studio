#!/usr/bin/env python3
"""Fixed JSON adapter. Never accepts filesystem paths in input."""
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


def _operation(projects, request,actor=None):
    fields(request, ['operation', 'projectId'], ['requestId', 'input', 'target', 'collection', 'versionId', 'subversionId', 'cursor', 'limit', 'exportId', 'offset', 'workflowId','previewId'])
    name = request['operation']
    if name not in ('read', 'initialize', 'overview', 'list', 'get', 'notes', 'current', 'revision', 'mutate', 'batch', 'export', 'json_export','import_preview','import_apply','import_preview_read','import_preview_chunk','import_receipt','export_info', 'export_chunk', 'workflows', 'workflow'):
        raise ProjectFault('Unsupported roadmap operation.', 400)
    if name in ('read', 'initialize'):
        fields(request, ['operation', 'projectId'], ['requestId'] if name == 'initialize' else [])
    elif name in ('mutate', 'batch', 'export','json_export','import_preview','import_apply'):
        fields(request, ['operation', 'projectId', 'input'])
    with connection(projects, request['projectId'], initialize=name == 'initialize') as db:
        if db is None:
            if name == 'workflows':
                fields(request, ['operation', 'projectId'], ['versionId', 'limit', 'cursor'])
                if 'cursor' in request: raise ProjectFault('No workflow page exists in this project.', 404)
                return {'items': [], 'nextCursor': None}
            if name not in ('read', 'overview') and not (name == 'current' and actor is not None):
                if name in ('mutate', 'batch') and actor is not None and 'editBinding' in actor:
                    raise ProjectFault('The project has no roadmap. Read its current state and use the returned initialize call.', 404)
                raise ProjectFault('Initialize this project roadmap before continuing.', 404)
            return {'exists': False, 'projectId': request['projectId']}
        if name in ('import_preview','import_apply'):
            from json_import import preview,apply_preview
            return preview(db,projects,request['projectId'],request['input'],actor) if name=='import_preview' else apply_preview(db,projects,request['projectId'],request['input'])
        if name in ('import_preview_read','import_preview_chunk'):
            from json_import import read_preview
            fields(request,['operation','projectId','previewId'],['offset','limit'] if name=='import_preview_chunk' else [])
            return read_preview(projects,request['projectId'],request['previewId'],request.get('offset',0) if name=='import_preview_chunk' else None,request.get('limit',8192))
        if name=='import_receipt':
            from validation import identity
            fields(request,['operation','projectId','requestId']);identity(request['requestId'])
            row=db.execute('SELECT result FROM receipts WHERE request_id=?',(request['requestId'],)).fetchone()
            if row is None:raise ProjectFault('Original import request not found.',404)
            value=json.loads(row[0])
            if 'previewId' not in value or value.get('confirmed') is not True:raise ProjectFault('This receipt belongs to another operation.',409)
            return value
        if name == 'batch':
            from batches import batch
            return batch(db,request['projectId'],request['input'],edit_binding=(actor or {}).get('editBinding'))
        if name == 'mutate':
            return mutate(db, request['projectId'], request['input'], edit_binding=(actor or {}).get('editBinding'))
        if name in ('workflows', 'workflow'):
            from workflow_reads import read as read_workflows
            return read_workflows(db, request['projectId'], request)
        if name in ('export','json_export'):
            return prepare(db, projects, request['projectId'], request['input'],json_mode=name=='json_export')
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


def operation(projects,request,proof=None,actor=None):
    if proof is None:return _operation(projects,request,actor)
    # Only the fixed browser adapter opts into this private envelope. Agent,
    # export and direct callers keep their existing public result contract.
    from generation import capture
    before=capture(projects,request['projectId'])
    result=_operation(projects,request,actor)
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
