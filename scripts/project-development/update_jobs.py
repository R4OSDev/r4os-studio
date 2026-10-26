"""Strict update installation admissions; no caller-selected command, VM or guest path."""
import uuid
from contracts import DevelopmentFault, identity, encode, hash_value
from jobs import now
from package_jobs import artifact
from update_plans import batch
import update_state as state

def transfers(store,ids,binding):
    if not isinstance(ids,list) or not 1<=len(ids)<=16 or len(set(ids))!=len(ids):raise DevelopmentFault('Select 1–16 distinct published transfer jobs.',400)
    result=[]
    for ident in ids:
        job=store.get(identity(ident));value=job.get('updateTransfer') or {}
        if job['kind']!='update_transfer' or job['state']!='completed' or not value.get('published'):
            raise DevelopmentFault('Only a confirmed published Inbox transfer can be installed.')
        from inbox_sftp import inbox_path
        final=inbox_path(value.get('final'),'R4U')
        if value.get('guestPath')!='C:'+final[2:].replace('/',chr(92)):raise DevelopmentFault('The published native path differs from its reserved transport name.')
        target=value.get('target') or {}
        if any(target.get(key)!=binding.get(other) for key,other in [('vmId','id'),('vmRevision','revision'),('imageSha256','imageSha256'),('systemGeneration','systemGeneration')]):
            raise DevelopmentFault('The Inbox package belongs to another VM/system binding.')
        package=artifact(store,job['packageArtifactId'])
        if package!=job['updatePackage'] or value['sha256']!=package['sha256'] or value['bytes']!=package['bytes'] or package['plan']['pins']!=store.project['pins']:
            raise DevelopmentFault('The published transfer differs from its immutable project package.')
        result.append({'jobId':ident,'transfer':value,'package':package})
    batch(store,[item['package']['plan']['id'] for item in result])
    if len({item['package']['plan']['metadata']['packageId'].casefold() for item in result})!=len(result):
        raise DevelopmentFault('Native batches require distinct package IDs.',400)
    return result

def admit(store,kind,request,owner,binding):
    fields={'requestId','projectRevision','transferJobIds'} if kind=='update_install' else {'requestId','projectRevision','updateId','updateRevision','batchId','targetRelease','vmRevision','confirmReboot'}
    if not isinstance(request,dict) or set(request)!=fields:raise DevelopmentFault('Unexpected update action fields.',400)
    identity(request['requestId']);owner=owner or {'sessionId':None,'agentRunId':None}
    fingerprint=hash_value({'kind':kind,'request':request,'owner':owner})
    previous=store.db.execute('SELECT id,request_hash FROM jobs WHERE request_id=?',(request['requestId'],)).fetchone()
    if previous:
        if previous['request_hash']!=fingerprint:raise DevelopmentFault('This update request ID already belongs to another action.')
        return store.get(previous['id']),False
    if type(request['projectRevision']) is not int or request['projectRevision']!=store.project['revision'] or not binding or binding['id']!=store.project['vmId']:
        raise DevelopmentFault('Project or assigned VM changed. Review the update action again.')
    extra={}
    if kind=='update_install':
        state.idle(store.projects,binding['id']);items=transfers(store,request['transferJobIds'],binding)
        extra={'updateTransfers':items,'updatePackage':items[0]['package'],'updateId':str(uuid.uuid4())}
    else:
        value=state.read(store,identity(request['updateId']),current=True)
        if (value['phase']!='awaiting_commit' or value['revision']!=request['updateRevision'] or value.get('batchId')!=request['batchId']
                or value['targetRelease']!=request['targetRelease'] or value['vmRevision']!=request['vmRevision']
                or value['vmId']!=binding['id'] or binding['revision']!=request['vmRevision'] or request['confirmReboot'] is not True
                or value['imageSha256']!=binding['imageSha256'] or value.get('systemGeneration')!=binding.get('systemGeneration')):
            raise DevelopmentFault('Confirm the current own VM, batch, target release and reboot effect.')
        extra={'updateId':value['id'],'updateRevision':value['revision'],'updatePackage':artifact(store,value['packageArtifactIds'][0])}
    store.db.execute('BEGIN IMMEDIATE')
    try:
        if store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchone():raise DevelopmentFault('This project already has an active development job.')
        job={'id':str(uuid.uuid4()),'projectId':store.id,'kind':kind,'state':'queued','revision':1,**owner,**extra,
            'artifactId':None,'deploymentId':None,'target':None,'process':None,'exitCode':None,'error':None,'phase':'queued','check':None,
            'source':None,'createdAt':now(),'completedAt':None,'projectRevision':store.project['revision'],'pins':store.project['pins'],
            'settingsRevision':store.settings()['revision'],'settings':store.settings(),'binding':binding}
        store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,1,1,?)',(job['id'],request['requestId'],fingerprint,kind,'queued',encode(job)))
        store.db.commit();return job,True
    except BaseException:store.db.rollback();raise
