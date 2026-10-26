"""Invalidate mutable guest readiness/deployment bindings without changing base image or project pins."""
import uuid
from contracts import DevelopmentFault,identity
from jobs import folder,now
from layout import save
from update_state import read_file

def epoch(projects,vm_id):
    path=folder(projects/'.studio/development/UpdateEpochs')/(identity(vm_id)+'.json')
    return read_file(path)['epoch'] if path.exists() or path.is_symlink() else None

def invalidate(store,record,operation):
    from access import Access
    value={'schema':1,'vmId':record['vmId'],'epoch':str(uuid.uuid4()),'updateId':record['id'],'operation':operation,'createdAt':now()}
    save(folder(store.projects/'.studio/development/UpdateEpochs')/(record['vmId']+'.json'),value)
    access=Access(store.projects,store.r4os,None);old=access.record(record['vmId']);old.pop('readiness',None)
    old['lastUpdateInvalidation']={key:value[key] for key in ('epoch','updateId','operation','createdAt')}
    access.save_record(record['vmId'],old)
    return value['epoch']

def require_deployment(store,deployment):
    target=deployment['target']
    if target.get('updateEpoch')!=epoch(store.projects,target['vmId']):
        raise DevelopmentFault('The guest system changed after this deployment. Deploy again before running.')
