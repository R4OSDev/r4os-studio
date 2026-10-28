"""Browser-only fixed JSON adapter. Not registered with any agent broker."""
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(1,str(Path(__file__).resolve().parents[1]/'projects'))
from store import ProjectFault
from board_store import connection
from board_validation import fields,identity
from board_model import listing,snapshot,receipt
from board_mutations import mutate

def operation(projects,request):
    fields(request,('operation','projectId'),('boardId','requestId','input'))
    project_id=identity(request['projectId']);op=request['operation']
    if op not in ('list','get','receipt','create','update','reorder'):raise ProjectFault('Unsupported browser Board operation.',400)
    if 'boardId' in request:identity(request['boardId'])
    with connection(projects,project_id,op=='create') as db:
        if db is not None and op in ('list','get','receipt'):db.execute('BEGIN')
        if op=='list':return listing(db,project_id)
        if op=='receipt':return receipt(db,identity(request['requestId']))
        if db is None:raise ProjectFault('Board not found in this project.',404)
        if op=='get':return snapshot(db,project_id,identity(request['boardId']))
        return mutate(db,project_id,op,request['input'],request.get('boardId'))

if __name__=='__main__':
    os.umask(0o077)
    try:
        raw=sys.stdin.buffer.read(131073)
        if len(raw)>131072:raise ProjectFault('Board input exceeds128 KiB.',413)
        result=operation(Path(sys.argv[1]),json.loads(raw));print(json.dumps({'result':result},ensure_ascii=False))
    except ProjectFault as error:print(json.dumps({'error':str(error),'code':error.code}));sys.exit(1)
    except sqlite3.IntegrityError:print(json.dumps({'error':'This Board name or parent relationship conflicts with existing data. Reload before changing it.','code':409}));sys.exit(1)
    except Exception:print(json.dumps({'error':'Board storage is unavailable. Preserve the original request ID and inspect its receipt. Existing data was preserved.','code':503}));sys.exit(1)
