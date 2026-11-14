"""Portable JSON v1, streamed from one immutable SQLite snapshot."""
import json
from model import common,item,version_fields
from reads import root_row
from storage import RoadmapFault
from validation import fields,identity,target

SCHEMA='r4os-studio-roadmap'
VERSION=1

def selection(db,body,verify=True):
    scope=body.get('scope')
    if scope not in ('roadmap','version','subversion'):raise RoadmapFault('scope must be roadmap, version or subversion.',400)
    required=['versionId'] if scope=='version' else ['versionId','subversionId'] if scope=='subversion' else []
    fields(body,['requestId','expectedRevision','currentVersionId','scope',*required])
    if scope=='roadmap':return root_row(db) if verify else None
    reference={'kind':scope,'id':identity(body['versionId'] if scope=='version' else body['subversionId'])}
    if scope=='subversion':reference['versionId']=identity(body['versionId'])
    return target(db,reference) if verify else None

def encoded(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def object_parts(value,children=()):
    yield encoded(value)[:-1]
    for key,values in children:
        yield ','+encoded(key)+':[';first=True
        for parts in values:
            if not first:yield ','
            first=False;yield from parts
        yield ']'
    yield '}'

def version_parts(db,row):
    value={**version_fields(row),'number':f'{row["major"]}.{row["minor"]}.X','title':row['title'],'vision':row['vision'],'status':row['status'],'order':row['position']}
    children=(subversion_parts(db,r) for r in db.execute('SELECT * FROM subversions WHERE version_id=? ORDER BY position,patch,id',(row['id'],)))
    yield from object_parts(value,[('subversions',children)])

def subversion_parts(db,row):
    from issue_origin import source_fields
    parent=db.execute('SELECT major,minor FROM versions WHERE id=?',(row['version_id'],)).fetchone()
    value={**version_fields(row),'versionId':row['version_id'],'number':f'{parent["major"]}.{parent["minor"]}.{row["patch"]}','title':row['title'],'description':row['description'],'status':row['status'],'order':row['position']}
    value.update(source_fields(db,row['id']))
    children=[(table,([encoded(item(r))] for r in db.execute('SELECT * FROM '+table+' WHERE subversion_id=? ORDER BY position,id',(row['id'],)))) for table in ('tasks','acceptances')]
    yield from object_parts(value,children)

def archive_references(db,scope,version_id):
    for row in db.execute("SELECT id,version_id,phase,payload FROM workflows WHERE kind='cleanup' ORDER BY created_at,id"):
        if scope!='roadmap' and row['version_id']!=version_id:continue
        payload=json.loads(row['payload']);saved=payload.get('archive')
        if not saved:continue
        yield {'workflowId':row['id'],'versionId':row['version_id'],'phase':row['phase'],'number':payload.get('number'),
               'archive':{k:saved[k] for k in ('path','sha256','byteLength','exportId','encoding') if k in saved},'subtreeIncluded':False}

def document(db,project_id,body,export_id,created_at):
    row=selection(db,body);root=root_row(db);scope=body['scope'];version_id=body.get('versionId',root['current_version_id'])
    header={'schema':SCHEMA,'schemaVersion':VERSION,'scope':scope,
            'source':{'projectId':project_id,'roadmapId':root['id'],'revision':root['revision'],'currentVersionId':root['current_version_id'],'exportId':export_id,'createdAt':created_at},
            'completeness':{'storedTreeComplete':True,'archivedTreesIncluded':False}}
    yield encoded(header)[:-1]+',"archiveReferences":['
    first=True
    for reference in archive_references(db,scope,version_id):
        if not first:yield ','
        first=False;yield encoded(reference)
    yield '],"data":'
    if scope=='roadmap':
        value={**common(root),'projectId':project_id,'description':root['description'],'currentVersionId':root['current_version_id']}
        yield from object_parts(value,[('versions',(version_parts(db,v) for v in db.execute('SELECT * FROM versions ORDER BY position,major,minor,id')))])
    elif scope=='version':yield from version_parts(db,row)
    else:yield from subversion_parts(db,row)
    yield '}\n'
