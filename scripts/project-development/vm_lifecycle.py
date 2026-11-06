"""Assigned-VM graceful stop/restart; original effects are never replayed."""
import asyncio
from contextlib import closing
from types import SimpleNamespace

from contracts import DevelopmentFault,UnconfirmedGuestEffect,LIMITS
from jobs import Jobs,folder,now
from layout import save

KINDS=('vm_stop','vm_restart')

def binding_fields(job):
    return {'schema':1,'jobId':job['id'],'vmId':job['binding']['id'],'vmRevision':job['binding']['revision'],
        'imageId':job['binding']['imageId'],'imageSha256':job['binding']['imageSha256'],'projectRevision':job['projectRevision'],
        'sessionId':job['sessionId'],'agentRunId':job['agentRunId']}


def validate_lease(projects,lease,cleanup=False,*,check_vm_metadata=True):
    """Bridge authority checks VM metadata; sandboxed workers retain local checks."""
    scope=lease['scope'];kind=scope.get('lifecycleKind')
    if kind not in KINDS or scope.get('kind')!='job':raise DevelopmentFault('This lease has no project VM lifecycle authority.',403)
    with closing(Jobs(projects,scope['r4os'],scope['projectId'])) as store:
        job=store.get(scope['jobId'])
        from authorization import authorize_job
        if not cleanup:authorize_job(store,job)
        binding=job.get('binding') or {}
        if (job['kind']!=kind or (job['state']!='running' and not cleanup) or binding.get('id')!=lease['vmId']
                or (not cleanup and (store.project['vmId']!=lease['vmId'] or store.project['revision']!=job['projectRevision'] or store.project['pins']!=job['pins']))
                or scope['projectRevision']!=job['projectRevision']
                or any(binding.get(key)!=scope.get(field) for key,field in (('revision','vmRevision'),('imageId','imageId'),('imageSha256','imageSha256')))):
            raise DevelopmentFault('The original VM lifecycle/project binding changed.',403)
        if cleanup:return {'kind':kind,**(job.get('vmLifecycle') or {'phase':'cleanup'})}
        if check_vm_metadata:
            from access import vm_config
            current=vm_config(scope['r4os'],lease['vmId'])
            if any(current[key]!=binding[key] for key in ('revision','imageId','imageSha256')):
                raise DevelopmentFault('The original VM image or settings revision changed.')
        from update_state import idle
        idle(projects,lease['vmId'])
        from quarantine import path
        if path(projects,lease['vmId']).exists():raise DevelopmentFault('Resolve the original unconfirmed guest effect before a VM power action.')
        value=job.get('vmLifecycle') or {'phase':'preparing'}
        if kind=='vm_restart' and 'accessRevision' in value:
            from access import Access,transport_profile
            transport_profile();record=Access(projects,scope['r4os'],None).record(lease['vmId'])
            if not record['enabled'] or record['revision']!=value['accessRevision']:
                raise DevelopmentFault('The original saved VM access changed during restart.')
        return {'kind':kind,**value}


async def bind(host,request,peer_pid):
    from lease import inspect
    from authorization import authorize_job
    from access import vm_config,transport_profile
    from vm_client import vm_call
    if set(request)!={'operation','projectId','jobId','leaseId','token'}:raise DevelopmentFault('Invalid VM lifecycle binding.',400)
    lease=inspect(host.config['projects'],request['leaseId'],request['token'],check_boot=False)
    scope=lease['scope']
    if (lease['pid']!=peer_pid or scope.get('kind')!='job' or scope.get('projectId')!=request['projectId']
            or scope.get('jobId')!=request['jobId']):raise DevelopmentFault('This VM lifecycle reservation belongs to another worker.',403)
    with closing(host.store(request['projectId'])) as store:
        job=store.get(request['jobId']);authorize_job(store,job)
        if job['kind'] not in KINDS or job.get('vmLifecycle'):raise DevelopmentFault('Read the original lifecycle job; it was not rebound.')
        vm=vm_config(store.r4os,lease['vmId']);info=await vm_call(SimpleNamespace(id=request['leaseId'],token=request['token']),'lifecycle_info')
        if info['vm']['state']!='running':raise DevelopmentFault('The assigned VM is no longer running. Use Start for a stopped VM.')
        if not info['process'] or not info['unit']['invocationId'] or info['unit']['controlPid']!='0':
            raise DevelopmentFault('The original VM process or transition worker is unconfirmed. No power action was sent.')
        boot=await host.boots.ensure(vm,info['unit']['invocationId'])
        value={**binding_fields(job),'kind':job['kind'],'phase':'bound','boundAt':now(),
            'original':{'unit':info['unit'],'process':info['process'],'bootId':boot['bootId']}}
        if job['kind']=='vm_restart':
            transport_profile();access=host.access.public(vm['id'])
            if not access['available']:raise DevelopmentFault(access['reason'])
            value['accessRevision']=access['revision']
        store.update(job['id'],vmLifecycle=value);return value


class VmLifecycle:
    def __init__(self,store,job):
        self.store,self.job=store,job
        self.work=folder(store.root/'VmLifecycleWork'/job['id']);self.log=store.evidence(job['id'])/'output.log'

    def record(self,phase,**fields):
        value={**(self.store.get(self.job['id']).get('vmLifecycle') or {}),**binding_fields(self.job),'kind':self.job['kind'],'phase':phase,**fields}
        self.store.update(self.job['id'],phase=phase,vmLifecycle=value)
        with self.log.open('ab') as stream:stream.write((phase.replace('_',' ').capitalize()+'\n').encode())
        return value

    async def run(self):
        from queue_lease import reserve
        from vm_worker import guard,broker_call
        from vm_client import vm_call
        from quarantine import path
        store,job=self.store,self.job;vm=job['binding']
        scope={'kind':'job','projectId':store.id,'projectRevision':job['projectRevision'],'jobId':job['id'],
            'vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256'],
            'lifecycleKind':job['kind'],'r4os':str(store.r4os)}
        async with reserve(store,job,scope,timeout=0) as lease:
            try:return await self.run_reserved(lease,scope)
            except BaseException as error:
                if interrupted_effect(store,job) or getattr(error,'uncertain',False):
                    quarantine_unknown(store,job,str(error) or 'Original VM lifecycle interrupted.')
                raise

    async def run_reserved(self,lease,scope):
        from vm_worker import guard,broker_call
        from vm_client import vm_call
        from quarantine import path
        store,job=self.store,self.job;vm=job['binding']
        guard(store,job,lease)
        if path(store.projects,vm['id']).exists():raise DevelopmentFault('Resolve the original unconfirmed guest effect before controlling this VM.')
        info=await vm_call(lease,'lifecycle_info')
        if info['fullyStopped']:
            if job['kind']=='vm_restart':raise DevelopmentFault('The assigned VM is stopped. Use Start project VM instead of Restart.')
            if not info['exportComplete']:raise DevelopmentFault('The stopped VM still needs Exchange synchronization. No power action was sent.')
            value=self.record('stopped',noop=True,stopped={'confirmed':True,'observedAt':now(),'unit':info['unit'],'exchange':info['vm'].get('shareSync')})
            save(self.work/'stopped.json',value)
            return store.update(job['id'],'completed',phase='stopped',exitCode=0,error=None)
        if info['vm']['state']!='running':raise DevelopmentFault('Wait for the assigned VM to finish its current start/stop transition. No power action was sent.')
        await broker_call({'operation':'bind_vm_lifecycle','projectId':store.id,'jobId':job['id'],'leaseId':lease.id,'token':lease.token})
        guard(store,job,lease)
        intent=self.work/'shutdown-intent.json'
        if intent.exists():raise UnconfirmedGuestEffect('This original shutdown already has an intent. Inspect it without another power action.')
        value=self.record('shutdown_intent',shutdownIntentAt=now());save(intent,value)
        try:await vm_call(lease,'shutdown')
        except DevelopmentFault as error:
            if error.code<500:raise
            raise UnconfirmedGuestEffect('The original graceful shutdown response is unconfirmed. It was not repeated.') from None
        self.record('waiting_for_shutdown',shutdownDispatched=True)
        deadline=asyncio.get_running_loop().time()+LIMITS['vmStopTimeoutSeconds']
        while True:
            guard(store,job,lease);info=await vm_call(lease,'lifecycle_info')
            if info['fullyStopped'] and not info['originalProcessAlive']:
                if not info['exportComplete']:
                    self.record('export_failed',qemuEnded=True,observedAt=now(),unit=info['unit'])
                    raise DevelopmentFault('QEMU ended but its Exchange export is incomplete or failed. No restart was sent.')
                value=self.record('stopped',stopped={'confirmed':True,'observedAt':now(),'unit':info['unit'],'exchange':info['vm'].get('shareSync')})
                save(self.work/'stopped.json',value);break
            if asyncio.get_running_loop().time()>=deadline:
                raise UnconfirmedGuestEffect('The original VM shutdown/export did not end before its deadline. No Force Stop or restart was sent.')
            await asyncio.sleep(.5)
        if job['kind']=='vm_stop':return store.update(job['id'],'completed',phase='stopped',exitCode=0,error=None)
        guard(store,job,lease)
        self.record('restart_intent',restartIntentAt=now())
        from vm_start import VmStart
        return await VmStart(store,store.get(job['id'])).run_reserved(lease,scope)


def interrupted_effect(store,job):
    value=store.get(job['id']).get('vmLifecycle') or {}
    # An interrupted, confirmed stop before start remains an honest stopped
    # receipt. Pending power phases remain unknown and are never resumed.
    return value.get('phase') in ('shutdown_intent','waiting_for_shutdown','restart_intent') and not (
        value.get('phase')=='waiting_for_shutdown' and (value.get('stopped') or {}).get('confirmed'))


def quarantine_unknown(store,job,message):
    from quarantine import path,claim
    target=job['binding']['id']
    marker=path(store.projects,target)
    if marker.exists() or marker.is_symlink():return
    claim(store.projects,target,{'jobId':job['id'],'projectId':store.id,'kind':job['kind'],
        'vmRevision':job['binding']['revision'],'reason':message,
        'phase':(store.get(job['id']).get('vmLifecycle') or {}).get('phase')})


def recovered(store,job):
    from recovery import read,receipt
    work=store.root/'VmLifecycleWork'/job['id']
    path=work/('ready.json' if job['kind']=='vm_restart' else 'stopped.json')
    if not path.exists():return None
    proof=read(path)
    if any(proof.get(k)!=v for k,v in binding_fields(job).items()) or not proof.get('stopped',{}).get('confirmed'):
        raise DevelopmentFault('The original lifecycle receipt has another owner or target. Existing files were preserved.')
    extra={}
    if job['kind']=='vm_restart':
        ready=proof.get('vmStart') or {}
        if (not ready.get('ready') or ready.get('bootId')!=proof.get('newBootId') or ready.get('bootId')==proof.get('original',{}).get('bootId')
                or any(ready.get(k)!=job['binding'][v] for k,v in [('vmId','id'),('vmRevision','revision'),('imageId','imageId'),('imageSha256','imageSha256')])):
            raise DevelopmentFault('The original restart has no confirmed new SSH/VER readiness receipt.')
        extra['vmStart']=ready
    return store.recovered(job['id'],'completed',receipt('original-vm-lifecycle',historical=True,jobId=job['id']),
        vmLifecycle=proof,exitCode=0,error=None,**extra)
