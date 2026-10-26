"""Durable project update records and the latest owner of a native VM update."""
import json
from pathlib import Path
from contracts import DevelopmentFault, identity, encode
from jobs import folder, now
from layout import save

TERMINAL={'live_installed','installed','rolled_back','aborted','rejected'}

def read_file(path):
    try:
        info=path.lstat()
        if path.resolve(strict=True)!=path or not path.is_file() or info.st_nlink!=1 or info.st_size>2097152:raise ValueError()
        value=json.loads(path.read_text())
        if not isinstance(value,dict) or value.get('schema')!=1:raise ValueError()
        return value
    except (OSError,ValueError):raise DevelopmentFault('The durable update record is unavailable. Preserve it for recovery.') from None

def owner_path(projects,vm_id):
    return folder(Path(projects)/'.studio/development/UpdateOwners')/(identity(vm_id)+'.json')

def owner(projects,vm_id):
    path=owner_path(projects,vm_id)
    return read_file(path) if path.exists() or path.is_symlink() else None

def idle(projects,vm_id):
    value=owner(projects,vm_id)
    if value and value['phase'] not in TERMINAL:
        raise DevelopmentFault('This VM has an owned update requiring commit or recovery. Inspect its original update record.')

def read(store,ident,current=False):
    value=read_file(store.root/'Updates'/identity(ident)/'update.json')
    if value['id']!=ident or value['projectId']!=store.id:raise DevelopmentFault('This update belongs to another project.')
    if current and owner(store.projects,value['vmId'])!=value:
        raise DevelopmentFault('This is no longer the exact current VM update owner. No native write was authorized.')
    return value

def write(store,value):
    value={**value,'revision':value.get('revision',0)+1,'updatedAt':now()}
    if len(encode(value).encode())>2097152:raise DevelopmentFault('The original update history reached its bounded receipt quota. Preserve it for explicit maintenance.')
    save(folder(store.root/'Updates'/value['id'])/'update.json',value)
    save(owner_path(store.projects,value['vmId']),value)
    return value

def listing(store):
    root=store.root/'Updates'
    if not root.exists():return []
    entries=sorted(root.iterdir())
    if len(entries)>4096:raise DevelopmentFault('Too many update records; archive them through explicit maintenance.')
    values=[read(store,item.name) for item in entries]
    fields=('schema','id','projectId','jobId','revision','phase','vmId','vmRevision','targetRelease','createdAt','updatedAt','batchId','transactions','packageArtifactIds','transferJobIds','installationConfirmed','rollbackConfirmed','abortConfirmed','cleanupConfirmed')
    return [{key:value[key] for key in fields if key in value} for value in sorted(values,key=lambda value:value['createdAt'],reverse=True)[:100]]

def matches(status,record):
    value=status['status']
    return (value['directoriesReady'] and value==record.get('lastStatus',{}).get('status')
            and (not record.get('batchId') or value.get('batchId')==record['batchId']))
