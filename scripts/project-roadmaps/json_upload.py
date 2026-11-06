"""Seal original uploaded/inline/workspace JSON in the existing export vault."""
import ctypes
import fcntl
import hashlib
import json
import os
import stat
import uuid
from exports import cache_directory,folder,open_archive,public,quota,record_receipt
from json_contract import MAX_BYTES,parse
from layout import sync
from reads import root_row
from storage import RoadmapFault,timestamp
from validation import identity

def upload(db,projects,project_id,file_id,raw,expected_hash=None,expected_size=None):
    identity(file_id);digest=hashlib.sha256(raw).hexdigest()
    if expected_hash is not None and digest!=expected_hash or expected_size is not None and len(raw)!=expected_size:raise RoadmapFault('Original JSON file hash or byte length changed.',409)
    doc=parse(raw);fingerprint=hashlib.sha256(json.dumps({'operation':'json_upload','projectId':project_id,'fileId':file_id,'sha256':digest,'byteLength':len(raw)},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    directory=cache_directory(projects,project_id,create=True);lock=os.open(directory/'.write.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode) or os.fstat(lock).st_nlink!=1:raise RoadmapFault('Invalid JSON upload lock.',503)
        fcntl.flock(lock,fcntl.LOCK_EX)
        destination=directory/file_id
        if destination.exists() or destination.is_symlink():
            with open_archive(projects,project_id,file_id) as (info,stream):
                if info.get('format')!='json' or info['sha256']!=digest or info['byteLength']!=len(raw):raise RoadmapFault('This original fileId belongs to different JSON bytes.',409)
                from exports import manifest
                if manifest(directory,project_id,file_id)['requestHash']!=fingerprint:raise RoadmapFault('This original fileId belongs to another operation.',409)
                return info
        old=db.execute('SELECT request_hash FROM receipts WHERE request_id=?',(file_id,)).fetchone()
        if old:raise RoadmapFault('This original fileId was already used.',409)
        quota(directory);scope=doc['scope'];data=doc['data']
        if scope=='roadmap':
            version_id=data['currentVersionId'];version=next(v for v in data['versions'] if v['id']==version_id);number=version['number']
        else:version_id=data['id'] if scope=='version' else data['versionId'];number=data['number']
        info={'schema':1,'id':file_id,'projectId':project_id,'roadmapId':doc['source']['roadmapId'],'versionId':version_id,'number':number,'filename':'roadmap.json' if scope=='roadmap' else number+'.json','revision':doc['source']['revision'],'currentVersionId':doc['source']['currentVersionId'],'encoding':'utf-8','byteLength':len(raw),'sha256':digest,'createdAt':timestamp(),'requestHash':fingerprint,'format':'json','scope':scope,'targetId':data['id'],'schemaVersion':1,'storedTreeComplete':True,'archivedTreesIncluded':False}
        stage=directory/('.stage-'+str(uuid.uuid4()));stage.mkdir(mode=0o700)
        for name,value in [('archive.json',raw),('export.json',json.dumps(info,ensure_ascii=False).encode())]:
            fd=os.open(stage/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
            with os.fdopen(fd,'wb') as stream:stream.write(value);stream.flush();os.fsync(stream.fileno())
        sync(stage);rename=ctypes.CDLL(None,use_errno=True).renameat2;rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint];rename.restype=ctypes.c_int
        if rename(-100,os.fsencode(stage),-100,os.fsencode(destination),1):raise OSError(ctypes.get_errno(),'JSON upload publication failed')
        sync(directory);result=public(info);record_receipt(db,file_id,fingerprint,result);return result
    finally:os.close(lock)
