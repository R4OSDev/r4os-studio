import datetime
import hashlib
import json
import uuid
from board_model import board,revision,summary
from board_validation import fields,identity,integer,text,name_key,order,MAX_BOARDS
from store import ProjectFault

def encode(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def mutate(db,project_id,operation,data,ident=None):
    fields(data,('requestId','expectedRevision'),('action','input','expectedOrderRevision') if operation=='mutate' else ('name','description','ids'))
    if 'name' in data:text(data['name'])
    if 'description' in data:text(data['description'],8000,True,True)
    rid=identity(data.get('requestId'));integer(data.get('expectedRevision'),0)
    try:fingerprint=hashlib.sha256(encode({'projectId':project_id,'operation':operation,'boardId':ident,'input':data}).encode()).hexdigest()
    except UnicodeError:raise ProjectFault('Board text contains invalid Unicode.',400) from None
    db.execute('BEGIN IMMEDIATE')
    try:
        previous=db.execute('SELECT fingerprint,result FROM requests WHERE id=?',(rid,)).fetchone()
        if previous:
            if previous[0]!=fingerprint:raise ProjectFault('This Board request ID belongs to different original input.',409)
            return json.loads(previous[1])
        if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]>=16000:raise ProjectFault('Board request storage is full. Existing data was preserved.',409)
        stamp=now();extra={}
        if operation=='create':
            fields(data,('requestId','expectedRevision','name'),('description',))
            if revision(db)!=data['expectedRevision']:raise ProjectFault('The Board list changed. Reload before creating.',409)
            name=text(data['name']);description=text(data.get('description',''),8000,True,True)
            if db.execute('SELECT COUNT(*) FROM boards').fetchone()[0]>=MAX_BOARDS:raise ProjectFault('This project reached its Board limit.',409)
            ident=str(uuid.uuid4());position=db.execute('SELECT COUNT(*) FROM boards').fetchone()[0]
            db.execute('INSERT INTO boards(id,name,name_key,description,position,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(ident,name,name_key(name),description,position,stamp,stamp))
            for index,title in enumerate(('To do','In progress','Done')):
                db.execute('INSERT INTO columns(id,board_id,title,position) VALUES(?,?,?,?)',(str(uuid.uuid4()),ident,title,index))
        elif operation=='update':
            fields(data,('requestId','expectedRevision'),('name','description'))
            if not set(data)&{'name','description'}:raise ProjectFault('Choose a Board field to change.',400)
            row=board(db,ident)
            if row['revision']!=data['expectedRevision']:raise ProjectFault('This Board changed. Your draft was preserved; reload before saving.',409)
            name=text(data.get('name',row['name']));description=text(data.get('description',row['description']),8000,True,True)
            db.execute('UPDATE boards SET name=?,name_key=?,description=?,revision=revision+1,updated_at=? WHERE id=?',(name,name_key(name),description,stamp,ident))
        elif operation=='reorder':
            fields(data,('requestId','expectedRevision','ids'))
            if revision(db)!=data['expectedRevision']:raise ProjectFault('The Board list changed. Reload before moving.',409)
            ids=order(data['ids'],[r[0] for r in db.execute('SELECT id FROM boards')])
            for position,key in enumerate(ids):db.execute('UPDATE boards SET position=? WHERE id=?',(position,key))
        elif operation=='mutate':
            fields(data,('requestId','expectedRevision','action','input'),('expectedOrderRevision',));row=board(db,ident)
            if row['revision']!=data['expectedRevision']:raise ProjectFault('This Board changed. Your draft was preserved; reload before saving.',409)
            if data['action'] in ('move_card','move_column'):
                if row['order_revision']!=integer(data.get('expectedOrderRevision')):raise ProjectFault('The Board order changed. Review the current order before moving.',409)
            elif 'expectedOrderRevision' in data:raise ProjectFault('This Board action does not accept an order revision.',400)
            from board_entries import apply
            extra=apply(db,ident,data['action'],data['input'],stamp)
        else:raise ProjectFault('Unsupported Board mutation.',400)
        db.execute('UPDATE meta SET revision=revision+1 WHERE singleton=1')
        result={'requestId':rid,'projectRevision':revision(db),**extra}
        if ident:result.update(boardId=ident,revision=board(db,ident)['revision'],board=summary(db,board(db,ident)))
        db.execute('INSERT INTO requests VALUES(?,?,?,?)',(rid,fingerprint,encode(result),stamp));db.commit();return result
    finally:
        if db.in_transaction:db.rollback()
