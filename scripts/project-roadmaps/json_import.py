"""Retained, file/revision-bound previews and one atomic original import."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid
from exports import open_archive,regular,quota
from import_plan import plan,validate,apply
from json_contract import MAX_BYTES,parse
from json_upload import upload
from layout import sync
from reads import root_row,binding
from storage import RoadmapFault,folder,timestamp
from validation import fields,identity,integer

MAX_PLAN_BYTES=64*1024*1024

def encoded(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
def fingerprint(value):return hashlib.sha256(encoded(value)).hexdigest()

@contextmanager
def vault(projects,project_id,create=False):
    directory=Path(projects)/project_id/'Roadmap/Imports'
    if create:directory.mkdir(mode=0o700,exist_ok=True)
    if not directory.exists():raise RoadmapFault('Original import preview not found.',404)
    folder(directory);fd=os.open(directory/'.write.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink!=1:raise RoadmapFault('Invalid import lock.',503)
        fcntl.flock(fd,fcntl.LOCK_EX);yield directory
    finally:os.close(fd)

@contextmanager
def open_plan(projects,project_id,preview_id):
    identity(preview_id);directory=Path(projects)/project_id/'Roadmap/Imports';folder(directory);path=directory/preview_id
    if not path.exists():raise RoadmapFault('Original import preview not found.',404)
    folder(path);regular(path/'manifest.json',8192);metadata=json.loads((path/'manifest.json').read_text())
    if metadata.get('schema')!=1 or metadata.get('projectId')!=project_id or metadata.get('previewId')!=preview_id:raise RoadmapFault('Original import preview binding changed.',409)
    info=regular(path/'plan.json',MAX_PLAN_BYTES);descriptor=os.open(path/'plan.json',os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(descriptor,'rb') as stream:
        before=os.fstat(stream.fileno());observed=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if observed(info)!=observed(before):raise RoadmapFault('Original import plan changed.',409)
        digest=hashlib.file_digest(stream,'sha256').hexdigest();after=os.fstat(stream.fileno())
        if observed(before)!=observed(after) or after.st_size!=metadata['byteLength'] or digest!=metadata['sha256']:raise RoadmapFault('Original import plan integrity check failed.',409)
        stream.seek(0);yield metadata,stream

def original(projects,project_id,preview_id):
    identity(preview_id)
    directory=Path(projects)/project_id/'Roadmap/Imports'
    if not directory.exists():raise RoadmapFault('Original import preview not found.',404)
    with open_plan(projects,project_id,preview_id) as (metadata,stream):raw=stream.read()
    value=json.loads(raw)
    if value.get('projectId')!=project_id or value.get('previewId')!=preview_id or value.get('fingerprint')!=metadata['fingerprint']:raise RoadmapFault('Original import plan binding changed.',409)
    return metadata,value,raw


def public(metadata,value):
    changes=[]
    for v in value['changes'][:50]:
        candidate={k:v[k] for k in ('kind','sourceId','targetId','action','fields')}
        if len(encoded(changes+[candidate]))>20000:break
        changes.append(candidate)
    mappings=value['mapping'][:50]
    return {'previewId':metadata['previewId'],'projectId':metadata['projectId'],'sha256':metadata['sha256'],'byteLength':metadata['byteLength'],
            'revision':value['expectedRevision'],'currentVersionId':value['currentVersionId'],'scope':value['scope'],'mode':value['mode'],
            'source':value['source'],'counts':value['counts'],'conflicts':value['conflicts'][:50],'conflictCount':len(value['conflicts']),
            'canApply':not value['conflicts'],'matching':value['matching'],'currentVersionChanged':False,'archiveReferencesIgnored':value['archiveReferencesIgnored'],
            'changes':changes,'mapping':mappings,'totalChanges':len(value['changes']),'detailsTruncated':len(changes)<len(value['changes']) or len(mappings)<len(value['mapping']),
            'readback':{'view':'import_preview_chunk','previewId':metadata['previewId'],'offset':0,'byteLimit':8192}}

def source(db,projects,project_id,rid,value,actor):
    if not isinstance(value,dict):raise RoadmapFault('source must select document, export or workspace.',400)
    kind=value.get('type')
    if kind=='export':
        fields(value,['type','exportId','sha256','byteLength']);identity(value['exportId'])
        with open_archive(projects,project_id,value['exportId']) as (info,stream):
            if info.get('format')!='json' or info['sha256']!=value['sha256'] or info['byteLength']!=value['byteLength']:raise RoadmapFault('Original JSON snapshot binding changed.',409)
            raw=stream.read(MAX_BYTES+1)
        return info,parse(raw)
    if kind=='document':fields(value,['type','document']);raw=encoded(value['document'])
    elif kind=='workspace':
        fields(value,['type','path','sha256','byteLength'])
        if actor is not None and not actor['config'].get('permissions',{}).get('studio.read_file'):raise RoadmapFault('Reading an import file requires Read file permission.',403)
        from cleanup_files import root
        path=value['path']
        if not isinstance(path,str) or not 1<=len(path)<=1024 or path.startswith('/') or '\\' in path or any(ord(c)<32 or ord(c)==127 for c in path) or any(p in ('','.','..') for p in path.split('/')) or len(path.split('/'))>32:raise RoadmapFault('Use an ordinary relative Workspace JSON file path.',400)
        with root(projects,project_id) as (fd,_):
            parent=os.dup(fd)
            try:
                parts=path.split('/')
                for name in parts[:-1]:
                    child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent);os.close(parent);parent=child
                opened=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
                with os.fdopen(opened,'rb') as stream:
                    before=os.fstat(stream.fileno())
                    if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>MAX_BYTES:raise RoadmapFault('Select a singly linked JSON file within 16 MiB.',400)
                    raw=stream.read(MAX_BYTES+1);after=os.fstat(stream.fileno());named=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)
                    signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                    if signature(before)!=signature(after) or signature(after)!=signature(named):raise RoadmapFault('The original Workspace JSON file changed while being read.',409)
            except OSError:raise RoadmapFault('The Workspace JSON file is unavailable or linked.',409) from None
            finally:os.close(parent)
        if len(raw)!=value['byteLength'] or hashlib.sha256(raw).hexdigest()!=value['sha256']:raise RoadmapFault('The original Workspace JSON hash or length changed.',409)
    else:raise RoadmapFault('source.type must be document, export or workspace.',400)
    file_id=str(uuid.uuid5(uuid.UUID(rid),'original-json-file'));info=upload(db,projects,project_id,file_id,raw)
    return info,parse(raw)

def preview(db,projects,project_id,body,actor=None):
    fields(body,['requestId','expectedRevision','currentVersionId','mode','target','source'],['numberPolicy'])
    rid=identity(body['requestId']);identity(body['currentVersionId']);integer(body['expectedRevision'],1,2**53-1)
    digest=fingerprint({'operation':'import_preview','projectId':project_id,**body})
    try:
        metadata,value,_=original(projects,project_id,rid)
        if metadata['fingerprint']!=digest:raise RoadmapFault('This preview requestId belongs to different input.',409)
        return public(metadata,value)
    except RoadmapFault as error:
        if error.code!=404:raise
    info,document=source(db,projects,project_id,rid,body['source'],actor)
    db.execute('BEGIN')
    try:
        root=root_row(db)
        if root['revision']!=body['expectedRevision'] or root['current_version_id']!=body['currentVersionId']:raise RoadmapFault('Roadmap revision changed. Prepare a fresh preview after reloading.',409)
        if db.execute("SELECT 1 FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted') LIMIT 1").fetchone():raise RoadmapFault('Reconcile the current roadmap workflow before importing.',409)
        value=plan(db,project_id,rid,document,body)
        if not value['conflicts']:
            try:validate(db,value,timestamp())
            except (RoadmapFault,sqlite3.IntegrityError) as e:value['conflicts'].append(str(e) if isinstance(e,RoadmapFault) else 'An import number or parent conflicts with an existing entry.')
        value.update(schema=1,projectId=project_id,previewId=rid,fingerprint=digest,expectedRevision=body['expectedRevision'],currentVersionId=body['currentVersionId'],scope=document['scope'],mode=body['mode'],
                     source={k:info[k] for k in ('id','sha256','byteLength','scope')},sourceProvenance=document['source'],target=body['target'],createdAt=timestamp())
    finally:db.rollback()
    raw=encoded(value)
    if len(raw)>MAX_PLAN_BYTES:raise RoadmapFault('The complete import preview exceeds 64 MiB.',413)
    metadata={'schema':1,'projectId':project_id,'previewId':rid,'fingerprint':digest,'sha256':hashlib.sha256(raw).hexdigest(),'byteLength':len(raw)}
    with vault(projects,project_id,create=True) as directory:
        destination=directory/rid
        if destination.exists():
            # Another identical preview may have won publication. Reconcile it.
            regular(destination/'manifest.json',8192);old=json.loads((destination/'manifest.json').read_text())
            if old['fingerprint']!=digest:raise RoadmapFault('This preview requestId belongs to different input.',409)
        else:
            quota(directory);stage=directory/('.stage-'+str(uuid.uuid4()));stage.mkdir(mode=0o700)
            for name,data in [('plan.json',raw),('manifest.json',encoded(metadata))]:
                fd=os.open(stage/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
                with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
            sync(stage);os.rename(stage,destination);sync(directory)
    metadata,value,_=original(projects,project_id,rid);return public(metadata,value)

def apply_preview(db,projects,project_id,body):
    fields(body,['requestId','previewId','previewSha256','expectedRevision','currentVersionId','confirm'])
    identity(body['requestId']);identity(body['previewId']);identity(body['currentVersionId']);integer(body['expectedRevision'],1,2**53-1)
    if body['confirm'] is not True or not isinstance(body['previewSha256'],str) or not re.fullmatch('[a-f0-9]{64}',body['previewSha256']):raise RoadmapFault('Confirm the exact original preview SHA-256 before applying.',400)
    digest=fingerprint({'operation':'import_apply','projectId':project_id,**body});db.execute('PRAGMA max_page_count='+str((64*1024*1024)//db.execute('PRAGMA page_size').fetchone()[0]));db.execute('BEGIN IMMEDIATE')
    try:
        old=db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?',(body['requestId'],)).fetchone()
        if old:
            if old['request_hash']!=digest:raise RoadmapFault('This import requestId belongs to different input.',409)
            return json.loads(old['result'])
        metadata,value,_=original(projects,project_id,body['previewId']);root=root_row(db)
        if metadata['sha256']!=body['previewSha256'] or value['expectedRevision']!=body['expectedRevision'] or value['currentVersionId']!=body['currentVersionId']:raise RoadmapFault('The original import preview binding changed.',409)
        if root['revision']!=body['expectedRevision'] or root['current_version_id']!=body['currentVersionId']:raise RoadmapFault('The roadmap changed. This preview cannot be applied; prepare a fresh preview.',409)
        if value['conflicts']:raise RoadmapFault('Resolve all preview conflicts before applying.',409)
        if db.execute("SELECT 1 FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted') LIMIT 1").fetchone():raise RoadmapFault('Reconcile the current roadmap workflow before importing.',409)
        if db.execute('SELECT count(*) FROM receipts').fetchone()[0]>=50000:raise RoadmapFault('Roadmap receipt storage needs maintenance.',503)
        with open_archive(projects,project_id,value['source']['id']) as (info,stream):
            if any(info[k]!=value['source'][k] for k in ('sha256','byteLength','scope')):raise RoadmapFault('The original import source changed.',409)
        now=timestamp();validate(db,value,now);apply(db,value,now)
        db.execute('UPDATE roadmap SET revision=revision+1,updated_at=?',(now,));result={**binding(db),'requestId':body['requestId'],'previewId':body['previewId'],'previewSha256':metadata['sha256'],'counts':value['counts'],'mapping':value['mapping'][:50],'totalMappings':len(value['mapping']),'mappingTruncated':len(value['mapping'])>50,'source':value['source'],'confirmed':True,'currentVersionChanged':False,'details':{'view':'import_preview_chunk','previewId':body['previewId'],'offset':0,'byteLimit':8192}}
        db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)',(body['requestId'],digest,result['revision'],encoded(result).decode(),now));db.commit();return result
    except sqlite3.IntegrityError:raise RoadmapFault('The import conflicts with current data. No changes were committed.',409) from None
    finally:db.rollback()

def read_preview(projects,project_id,preview_id,offset=None,limit=8192):
    metadata,value,raw=original(projects,project_id,preview_id)
    if offset is None:return public(metadata,value)
    integer(offset,0,len(raw));integer(limit,4,65536)
    end=min(len(raw),offset+limit)
    try:raw[:offset].decode('utf-8')
    except UnicodeError:raise RoadmapFault('Use the returned UTF-8 byte offset.',400) from None
    while True:
        try:text=raw[offset:end].decode('utf-8');break
        except UnicodeError:end-=1
    return {'previewId':preview_id,'sha256':metadata['sha256'],'byteLength':len(raw),'offset':offset,'nextOffset':end if end<len(raw) else None,'text':text}
