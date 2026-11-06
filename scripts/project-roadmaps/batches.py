"""Prevalidated dependent changes and their receipt in one original transaction."""
import hashlib
import json
import re
import sqlite3
from mutations import apply_change
from reads import binding,root_row
from storage import RoadmapFault,timestamp
from validation import fields,identity,integer

MAX_OPERATIONS=128

def apply_operations(db,operations,now,maximum=MAX_OPERATIONS):
    if not isinstance(operations,list) or not 1<=len(operations)<=maximum:
        raise RoadmapFault('operations must contain 1 to '+str(maximum)+' changes.',400)
    references={};results=[]
    def resolve(value,path):
        if isinstance(value,str) and value.startswith('$'):
            if value[1:] not in references:raise RoadmapFault(path+': unknown or forward local reference '+value[:65]+'.',400)
            return references[value[1:]]
        return value
    for index,operation in enumerate(operations):
        path='operations['+str(index)+']'
        fields(operation,['target','action'],['input','key'],context=path)
        if 'key' in operation:
            key=operation['key']
            if operation['action']!='create' or not isinstance(key,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',key) or key in references:
                raise RoadmapFault(path+'.key: use one unique local name on a create operation.',400)
        reference=operation['target']
        if not isinstance(reference,dict):raise RoadmapFault(path+'.target must be an object.',400)
        reference={key:resolve(value,path+'.target.'+key) if key in ('id','versionId','subversionId') else value for key,value in reference.items()}
        data=operation.get('input',{})
        if isinstance(data,dict) and isinstance(data.get('ids'),list):data={**data,'ids':[resolve(v,path+'.input.ids') for v in data['ids']]}
        try:changed=apply_change(db,reference,operation['action'],data,now)
        except (RoadmapFault,sqlite3.IntegrityError) as error:
            code=error.code if isinstance(error,RoadmapFault) else 409
            raise RoadmapFault(path+'.input/target: '+(str(error) if isinstance(error,RoadmapFault) else 'Entry conflicts with its parent, number or status.'),code) from None
        if 'key' in operation:references[operation['key']]=changed['id']
        results.append({'index':index,**({'key':operation['key']} if 'key' in operation else {}),'entity':changed})
    return {'operations':results,'references':references}

def validate_operations(db,operations,now,maximum=MAX_OPERATIONS):
    # A private SQLite clone validates all domain constraints before the first
    # source write. The original IMMEDIATE transaction holds a stable revision.
    clone=sqlite3.connect(':memory:')
    try:
        clone.deserialize(db.serialize());clone.row_factory=sqlite3.Row;clone.execute('PRAGMA foreign_keys=ON')
        result=apply_operations(clone,operations,now,maximum)
        if clone.execute('PRAGMA foreign_key_check').fetchone():raise RoadmapFault('operations contain an invalid parent binding.',400)
        return result
    finally:clone.close()

def batch(db,project_id,body):
    fields(body,['requestId','expectedRevision','currentVersionId','operations'])
    identity(body['requestId']);identity(body['currentVersionId']);integer(body['expectedRevision'],1,2**53-1)
    if len(json.dumps(body,ensure_ascii=False).encode())>128*1024:raise RoadmapFault('Batch input exceeds 128 KiB.',413)
    fingerprint=hashlib.sha256(json.dumps({'operation':'batch','projectId':project_id,**body},sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    db.execute('PRAGMA max_page_count='+str((64*1024*1024)//db.execute('PRAGMA page_size').fetchone()[0]));db.execute('BEGIN IMMEDIATE')
    try:
        receipt=db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?',(body['requestId'],)).fetchone()
        if receipt:
            if receipt['request_hash']!=fingerprint:raise RoadmapFault('This requestId belongs to different roadmap input.',409)
            return json.loads(receipt['result'])
        root=root_row(db)
        if root['revision']!=body['expectedRevision'] or root['current_version_id']!=body['currentVersionId']:raise RoadmapFault('The roadmap changed. Reload its revision before saving.',409)
        if db.execute("SELECT 1 FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted') LIMIT 1").fetchone():raise RoadmapFault('Reconcile the current roadmap workflow before editing.',409)
        if db.execute('SELECT count(*) FROM receipts').fetchone()[0]>=50000:raise RoadmapFault('Roadmap receipt storage needs maintenance.',503)
        now=timestamp();validate_operations(db,body['operations'],now)
        result=apply_operations(db,body['operations'],now)
        db.execute('UPDATE roadmap SET revision=revision+1,updated_at=?',(now,));result={**binding(db),'requestId':body['requestId'],**result}
        raw=json.dumps(result,ensure_ascii=False)
        if len(raw.encode())>1500000:raise RoadmapFault('Batch result exceeds its bounded receipt limit.',413)
        db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',(body['requestId'],fingerprint,result['revision'],raw,now));db.commit();return result
    except sqlite3.IntegrityError:raise RoadmapFault('Batch conflicts with the roadmap. No changes were committed.',409) from None
    finally:db.rollback()
