"""Assigned-VM lifecycle jobs with durable original power receipts."""
import asyncio
from contextlib import closing
from types import SimpleNamespace

from contracts import DevelopmentFault,UnconfirmedGuestEffect,LIMITS,identity
from jobs import Jobs,folder,now
from layout import save

KINDS=('vm_stop','vm_restart')
RESET_CONFIRM_SECONDS = 20


def validate_reset_input(store, request):
    from project_maintenance import pending_git
    if set(request) != {'requestId','projectRevision','settingsRevision','hardReset'} or request['hardReset'] is not True:
        raise DevelopmentFault('Use the explicit hard restart action.',400)
    identity(request['requestId'])
    if (type(request['projectRevision']) is not int or request['projectRevision'] != store.project['revision']
            or type(request['settingsRevision']) is not int or request['settingsRevision'] != store.settings()['revision']):
        raise DevelopmentFault('Project or Run & Test settings changed. Reload before starting.')
    if pending_git(store.projects, store.id):
        raise DevelopmentFault('Reconcile the original Git pull before another development job.')


def binding_fields(job):
    return {'schema':1,'jobId':job['id'],'vmId':job['binding']['id'],'vmRevision':job['binding']['revision'],
        'imageId':job['binding']['imageId'],'imageSha256':job['binding']['imageSha256'],'projectRevision':job['projectRevision'],
        'sessionId':job['sessionId'],'agentRunId':job['agentRunId'],**({'hardReset':True} if job.get('hardReset') else {})}


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
        if not job.get('hardReset') and path(projects,lease['vmId']).exists():
            raise DevelopmentFault('Resolve the original unconfirmed guest effect before a VM power action.')
        value=job.get('vmLifecycle') or {'phase':'preparing',**({'hardReset':True} if job.get('hardReset') else {})}
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
        hard = job.get('hardReset') is True
        if info['vm']['state'] not in (('running','paused') if hard else ('running',)):
            raise DevelopmentFault('The assigned VM is no longer running. Use Start for a stopped VM.')
        if not info['process'] or not info['unit']['invocationId'] or info['unit']['controlPid']!='0':
            raise DevelopmentFault('The original VM process or transition worker is unconfirmed. No power action was sent.')
        boot=await host.boots.ensure(vm,info['unit']['invocationId'],allow_paused=True) if hard else await host.boots.ensure(vm,info['unit']['invocationId'])
        value={**binding_fields(job),'kind':job['kind'],'phase':'bound','boundAt':now(),
            'original':{'unit':info['unit'],'process':info['process'],'bootId':boot['bootId']}}
        if job['kind']=='vm_restart' and not hard:
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
        if job.get('hardReset'): return await self.hard_reset(lease)
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

    async def hard_reset(self, lease):
        from vm_worker import guard, broker_call
        from vm_client import vm_call
        store, job = self.store, self.job
        intent = self.work / 'reset-intent.json'
        if intent.exists():
            raise UnconfirmedGuestEffect('This original VM reset already has an intent. Inspect its result.')
        await broker_call({'operation':'bind_vm_lifecycle','projectId':store.id,'jobId':job['id'],
                           'leaseId':lease.id,'token':lease.token})
        guard(store,job,lease)
        value = self.record('reset_intent', resetIntentAt=now())
        save(intent,value)
        acknowledged = False
        try:
            await vm_call(lease, 'restart')
            acknowledged = True
        except DevelopmentFault as error:
            if error.code < 500:
                self.record('reset_refused')
                raise
        self.record('waiting_for_reset', resetAcknowledged=acknowledged)
        deadline = asyncio.get_running_loop().time()+RESET_CONFIRM_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            guard(store,job,lease)
            proof = reset_proof(store, job, value, acknowledged)
            if proof:
                receipt = self.record('reset_confirmed', reset=proof, newBootId=proof['bootId'])
                save(self.work/'reset.json',receipt)
                return store.update(job['id'],'completed',phase='reset_confirmed',exitCode=0,error=None,
                    readiness={'state':'not-run','reason':'New VM boot confirmed. Guest SSH readiness has not been checked.'})
            await asyncio.sleep(.25)
        raise UnconfirmedGuestEffect('A new boot could not be confirmed after the original hard reset. Inspect its saved receipt.')


def reset_proof(store, job, lifecycle, acknowledged):
    from boot import saved_boot
    vm = job['binding']; original = lifecycle['original']
    boot = saved_boot(store.projects,vm['id']) or {}
    proof = boot.get('hostReset') or {}
    if proof.get('previousBootId') != original['bootId']: proof = boot.get('transition') or {}
    if (not boot.get('connected') or proof.get('kind') != 'qmp_reset' or proof.get('guest') is True
            or (not acknowledged and proof.get('guest') is not False)
            or boot.get('invocationId') != original['unit']['invocationId']
            or any(boot.get(k) != vm[source] for k,source in (('vmRevision','revision'),('imageId','imageId'),('imageSha256','imageSha256')))
            or proof.get('previousBootId') != original['bootId'] or proof.get('bootId') == original['bootId']
            or proof.get('resetAt',proof.get('observedAt','')) < lifecycle['resetIntentAt']): return
    return {**proof,'confirmed':True,'commandAcknowledged':acknowledged}


def interrupted_effect(store,job):
    value=store.get(job['id']).get('vmLifecycle') or {}
    # An interrupted, confirmed stop before start remains an honest stopped
    # receipt. Pending power phases remain unknown and are never resumed.
    return value.get('phase') in ('shutdown_intent','waiting_for_shutdown','restart_intent','reset_intent','waiting_for_reset') and not (
        value.get('phase')=='waiting_for_shutdown' and (value.get('stopped') or {}).get('confirmed'))


def quarantine_unknown(store,job,message):
    from quarantine import path,claim,resolve_after_boot
    target=job['binding']['id']
    marker=path(store.projects,target)
    if marker.exists() or marker.is_symlink():return
    lifecycle = store.get(job['id']).get('vmLifecycle') or {}
    original = lifecycle.get('original')
    value = {'jobId':job['id'],'projectId':store.id,'kind':job['kind'],
        'vmRevision':job['binding']['revision'],'reason':message,'phase':lifecycle.get('phase')}
    if original:
        value['target'] = {key:lifecycle[key] for key in ('vmId','vmRevision','imageId','imageSha256')}
        value['target']['bootId'] = original['bootId']
        value['effectStartedAt'] = lifecycle.get('resetIntentAt') or lifecycle.get('shutdownIntentAt')
    claim(store.projects,target,value)
    from boot import saved_boot
    boot = saved_boot(store.projects,target)
    if boot: resolve_after_boot(store.projects,boot)


def recovered(store,job):
    from recovery import read,receipt
    work=store.root/'VmLifecycleWork'/job['id']
    path=work/('reset.json' if job.get('hardReset') else 'ready.json' if job['kind']=='vm_restart' else 'stopped.json')
    if not path.exists():return None
    proof=read(path)
    if job.get('hardReset'):
        reset = proof.get('reset') or {}
        if (any(proof.get(k)!=v for k,v in binding_fields(job).items()) or reset.get('confirmed') is not True
                or reset.get('kind')!='qmp_reset' or reset.get('bootId')!=proof.get('newBootId')
                or reset.get('previousBootId')!=proof.get('original',{}).get('bootId')
                or reset.get('bootId')==reset.get('previousBootId')):
            raise DevelopmentFault('The original hard reset receipt has no confirmed new boot.')
        return store.recovered(job['id'],'completed',receipt('original-vm-hard-reset',historical=True,jobId=job['id']),
            vmLifecycle=proof,exitCode=0,error=None)
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
