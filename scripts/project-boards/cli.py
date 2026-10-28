"""Browser-only fixed JSON adapter. Not registered with any agent broker."""
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(1,str(Path(__file__).resolve().parents[1]/'projects'))
from store import ProjectFault
from board_store import connection,SUPPORTED_FEATURE_LEVEL
from board_validation import fields,identity,integer
from board_model import listing,snapshot,receipt,card,card_row,board,search
from board_mutations import mutate

def operation(projects,request):
    fields(request,('operation','projectId'),('boardId','requestId','cardId','input','clientLevel','query'))
    project_id=identity(request['projectId']);op=request['operation']
    if op not in ('list','get','receipt','create','update','reorder','mutate','card','search'):raise ProjectFault('Unsupported browser Board operation.',400)
    level=integer(request.get('clientLevel',1))
    if level>SUPPORTED_FEATURE_LEVEL:raise ProjectFault('Reload R4OS Studio to match the available Board features. Your data was preserved.',409)
    if op in ('mutate','card') and level<2:raise ProjectFault('Reload R4OS Studio to use Board cards and columns.',409)
    if (op=='search' or op=='mutate' and (request.get('input',{}).get('action') in ('create_label','update_label','delete_label') or set(request.get('input',{}).get('input',{}))&{'priority','dueDate','labelIds','checklist'})) and level<3:raise ProjectFault('Reload R4OS Studio to use Board metadata.',409)
    if 'boardId' in request:identity(request['boardId'])
    with connection(projects,project_id,op=='create',client_level=level) as db:
        if db is not None and op in ('list','get','receipt','card','search'):db.execute('BEGIN')
        if op=='list':return listing(db,project_id)
        if op=='receipt':return receipt(db,identity(request['requestId']))
        if db is None:raise ProjectFault('Board not found in this project.',404)
        if op=='get':return snapshot(db,project_id,identity(request['boardId']))
        if op=='search':return search(db,project_id,identity(request['boardId']),request['query'])
        if op=='card':
            parent=board(db,identity(request['boardId']))
            return {'card':card(db,card_row(db,request['boardId'],identity(request['cardId'])),True),'boardRevision':parent['revision']}
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
