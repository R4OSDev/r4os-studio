"""Native own-link launches, with the original Prepare request saved before Activate."""
import asyncio
import base64
import hashlib
import json
import os
import re
import struct
from contracts import DevelopmentFault, UnconfirmedGuestEffect, identity
from desktop_shortcuts import previous, link_path, content, DesktopRead
from deskrun import NotSubmitted
from jobs import now
from layout import save

PHASES = {0:'unavailable',1:'prepared',2:'accepted',3:'starting',4:'process',5:'ready',6:'ended',7:'cleaned',8:'rejected',9:'expired'}
ENDED, REAPED, RELEASED = 32, 64, 128


def publication(store, vm, deployment, settings):
    receipt = previous(store, vm)
    if (deployment.get('role') != 'desktop' or deployment.get('kind') != 'R4X'
            or deployment.get('helperCapabilities',{}).get('desktopLinkVersion') != 1):
        raise DevelopmentFault('Deploy this GUI artifact with a native-link-v1 helper before activating its shortcut.')
    if not receipt or receipt.get('deploymentId') != deployment['id'] or receipt.get('artifactId') != deployment['artifactId']:
        raise DevelopmentFault('Publish this exact verified deployment on the desktop before activating its shortcut.')
    text = receipt.get('content')
    if not isinstance(text,str): raise DevelopmentFault('The original desktop publication content is unavailable.')
    title = next((v[6:] for v in text.splitlines() if v.startswith('TITLE=')), None)
    if (receipt.get('path') != link_path(store.id) or receipt.get('fullReadbackVerified') is not True
            or text != content(store.project,deployment,title)
            or receipt.get('sha256') != hashlib.sha256(text.encode()).hexdigest()):
        raise DevelopmentFault('The original own-link publication binding is inconsistent.')
    if settings['arguments']:
        raise DevelopmentFault('Link activation uses the published link arguments. Clear the run arguments first.',400)
    return receipt.copy()


async def verify_files(ssh, receipt, deployment, guard=lambda:None):
    """Read exactly the published link and the immutable deployed app, without writes."""
    guest = '/' + deployment['guestDirectory'][0] + '/' + deployment['guestDirectory'][3:].replace('\\','/')
    app = next((v for v in deployment['files'] if v['path'].upper() == (guest+'/APP.R4X').upper()),None)
    if app is None: raise DevelopmentFault('The verified deployment has no exact APP.R4X record.')
    async with DesktopRead(ssh,[receipt['path']],guard) as reader:
        if await reader.text(receipt['path']) != receipt['content']:
            raise DevelopmentFault('The published desktop link changed. No application was started.')
        reader.paths[app['path']] = app['bytes']
        before = await reader.stat(app['path'])
        if before is None or not before['regular'] or before['bytes'] != app['bytes']:
            raise DevelopmentFault('The desktop target no longer matches the verified deployment.')
        handle = await reader.open(app['path']); count = 0; digest = hashlib.sha256()
        try:
            while True:
                guard(); chunk = await reader.read(handle,count)
                if not chunk: break
                count += len(chunk)
                if count > app['bytes']: raise DevelopmentFault('The desktop target changed during verification.')
                digest.update(chunk)
        finally: await reader.close(handle)
        if count != app['bytes'] or digest.hexdigest() != app['sha256'] or await reader.stat(app['path']) != before:
            raise DevelopmentFault('The desktop target bytes changed. No application was started.')


async def preflight(store, vm, deployment, settings, access):
    from access import SshTransport
    from lease import VmLease, inspect
    from vm_client import vm_call
    receipt = publication(store,vm,deployment,settings)
    scope = {'kind':'recovery','vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256']}
    async def inspect_current():
        with VmLease(store.projects,vm['id'],scope) as lease:
            info = await vm_call(lease,'info')
            if info['vm']['state'] != 'running': raise DevelopmentFault('Start the assigned VM before activating its shortcut.')
            check = lambda: inspect(store.projects,lease.id,lease.token)
            async with SshTransport(access,vm,lease) as ssh:
                await verify_files(ssh,receipt,deployment,check)
            return info
    # Stay within the existing coordinator request deadline, including SSH
    # opening and the full byte readback. This operation cannot activate a link.
    try: info = await asyncio.wait_for(inspect_current(),12)
    except (OSError,asyncio.TimeoutError,ValueError):
        raise DevelopmentFault('The current own-link and target could not be verified. No activation was submitted.') from None
    return {**receipt,'preflightAt':now(),'vmInvocationId':info['invocationId']}


def native_receipt(value, original, prepared=None, controller=None):
    identity(original['executionId'])
    if not isinstance(value,dict) or 'transportError' in value:
        raise UnconfirmedGuestEffect('The native link receipt is unavailable. Read the saved original request; never activate again.')
    q = value.get('nativeRequest')
    try: raw = base64.b64decode(q,validate=True)
    except (ValueError,TypeError): raise UnconfirmedGuestEffect('The native link request is malformed.') from None
    if len(raw) != 1296 or base64.b64encode(raw).decode() != q:
        raise UnconfirmedGuestEffect('The native link request has an unsupported Contract71 representation.')
    if struct.unpack_from('<II',raw,0)!=(1,96) or struct.unpack_from('<I',raw,268)[0]!=0:
        raise UnconfirmedGuestEffect('The original native link token version or reserved fields differ.')
    if (value.get('linkPath') != original['nativePath'] or value.get('linkContent') != original['content']
            or type(value.get('result')) is not int or not -10 <= value['result'] <= 0
            or type(value.get('phase')) is not int or value['phase'] not in PHASES
            or type(value.get('flags')) is not int or not 0 <= value['flags'] <= 255):
        raise UnconfirmedGuestEffect('The native link receipt differs from this original own-link intent.')
    if value['phase']==0 and value['result']==0:
        raise UnconfirmedGuestEffect('The native link status has no confirmed phase.')
    words = [str(v) for v in struct.unpack('<QQQ',hashlib.sha256(original['executionId'].encode()).digest()[:24])]
    if value.get('intent') != words: raise UnconfirmedGuestEffect('The native link correlation differs from the original execution.')
    service_id,service_reserved,service_generation=struct.unpack_from('<IIQ',raw,8)
    owner_id,owner_reserved,owner_generation=struct.unpack_from('<IIQ',raw,24)
    epoch=[str(v) for v in struct.unpack_from('<QQQ',raw,40)]
    raw_intent=[str(v) for v in struct.unpack_from('<QQQ',raw,64)]
    raw_path=raw[104:264].split(b'\0',1)[0]
    length=struct.unpack_from('<I',raw,264)[0]
    if (service_reserved or owner_reserved or length>1024 or epoch!=value.get('epoch') or not any(int(v) for v in epoch)
            or raw_intent!=words or raw_path!=original['nativePath'].encode() or raw[272:272+length]!=original['content'].encode()
            or any(raw[104+len(raw_path):264]) or any(raw[272+length:])
            or value.get('ownerId')!=owner_id or value.get('ownerGeneration')!=str(owner_generation)
            or value.get('serviceId')!=service_id or value.get('serviceGeneration')!=str(service_generation)
            or value.get('serial')!=str(struct.unpack_from('<Q',raw,88)[0])
            or value.get('deadline')!=str(struct.unpack_from('<Q',raw,96)[0])):
        raise UnconfirmedGuestEffect('The full canonical link request differs from its original ownership and content receipt.')
    for name in ('serial','deadline','ownerGeneration','serviceGeneration','desktopGeneration','processGeneration',
                 'acceptedTick','startedTick','readyTick','cleanupTick','contentGeneration'):
        text=value.get(name)
        if not isinstance(text,str) or not re.fullmatch(r'0|[1-9][0-9]{0,19}',text) or int(text)>2**64-1:
            raise UnconfirmedGuestEffect('The native link receipt has an invalid generation or clock.')
    for name in ('ownerId','serviceId','desktopId','processId'):
        if type(value.get(name)) is not int or not 0 <= value[name] <= 2**32-1:
            raise UnconfirmedGuestEffect('The native link receipt has an invalid process identity.')
    if not int(value['serial']) or not int(value['deadline']) or not value['ownerId'] or not int(value['ownerGeneration']) or not value['serviceId'] or not int(value['serviceGeneration']):
        raise UnconfirmedGuestEffect('The native link admission binding is incomplete.')
    if prepared and q != prepared['nativeRequest']: raise UnconfirmedGuestEffect('Native link status names another prepared operation.')
    if controller and (value['ownerId'],value['ownerGeneration']) != (controller['watchdogInstanceId'],controller['watchdogGeneration']):
        raise UnconfirmedGuestEffect('The native link activator differs from the original watchdog generation.')
    if bool(value['processId']) != bool(int(value['processGeneration'])) or bool(value['desktopId']) != bool(int(value['desktopGeneration'])):
        raise UnconfirmedGuestEffect('The native link receipt has a partial process identity.')
    if value['processId'] and (value.get('resolvedPath') != original['target'] or value.get('resolvedArguments') != ''
            or value.get('policy') != 2 or not int(value['processGeneration']) or not value['desktopId'] or not int(value['desktopGeneration'])):
        raise UnconfirmedGuestEffect('The actual native link target or process does not match the verified GUI deployment.')
    if value['phase'] in (4,5,6) and (not value['processId'] or not int(value['startedTick']) or value['flags']&16==0):
        raise UnconfirmedGuestEffect('The native process receipt is not validated.')
    if value['phase']==5 and (not int(value['readyTick']) or not int(value['contentGeneration'])):
        raise UnconfirmedGuestEffect('The native link has no actual ready frame receipt.')
    if value['flags']&ENDED:
        completion=value.get('completion')
        if (not isinstance(completion,dict) or not value['processId']
                or completion.get('processId')!=value['processId'] or completion.get('processGeneration')!=value['processGeneration']
                or not isinstance(completion.get('sequence'),str) or not re.fullmatch(r'[1-9][0-9]{0,19}',completion['sequence'])
                or int(completion['sequence'])>2**64-1 or type(completion.get('flags')) is not int
                or not 0<=completion['flags']<=2**32-1 or completion['flags']&1==0
                or type(completion.get('exitCode')) is not int or not -2**31<=completion['exitCode']<2**31
                or type(completion.get('exitReason')) is not int or not 0<=completion['exitReason']<=255):
            raise UnconfirmedGuestEffect('The original native process completion is inconsistent.')
    return value


def public(value):
    return {k:v for k,v in value.items() if k not in ('nativeRequest','epoch','intent','linkContent')}


def bound_original(store,job,original,intent):
    publication=job.get('desktopLinkPublication') or {}
    deployment=store.deployment_metadata(job['deploymentId'])
    identity(original['executionId'])
    if (original.get('schema')!=1 or original.get('jobId')!=job['id'] or original.get('projectId')!=store.id
            or original.get('deploymentId')!=job['deploymentId'] or original.get('executionId')!=intent.get('executionId')
            or original.get('vmInvocationId')!=intent.get('vmInvocationId') or original.get('publication')!=publication
            or original.get('nativePath')!=link_path(store.id).replace('/C/','C:\\',1).replace('/','\\')
            or original.get('content')!=publication.get('content')
            or original.get('target')!=deployment['guestDirectory']+'\\APP.R4X'):
        raise DevelopmentFault('The saved native link intent differs from its original job and publication.')


class DesktopLinkLaunch:
    def __init__(self, execution, ssh, deployment, lease):
        self.owner,self.ssh,self.deployment,self.lease=execution,ssh,deployment,lease
        self.store,self.job=execution.store,execution.job
        self.prepared=None;self.original=None;self.process=None;self.value=None;self.index=0
        self.status_expired=False;self.next_status=0
        self.activation_submitted=False

    def save(self,phase,value=None):
        self.index+=1
        if value is not None:
            save(self.owner.work/f'link-{self.index}.receipt.json',value)
            self.value=value
        self.store.update(self.job['id'],desktopLinkActivation={'version':1,'phase':phase,
            'publicationJobId':self.job['desktopLinkPublication']['jobId'],
            'linkPath':self.original['nativePath'],'linkSha256':self.job['desktopLinkPublication']['sha256'],
            'originalRequestSha256':hashlib.sha256(base64.b64decode(self.prepared['nativeRequest'])).hexdigest() if self.prepared else None,
            'native':public(value) if value else None,'checkedAt':now()})

    async def start(self):
        try:
            return await self._start()
        except (DevelopmentFault,OSError,ValueError) as error:
            if not self.activation_submitted:
                # Prepare and the exact-file checks cannot start an app. Keep
                # helper cleanup separate from an uncertain Activate.
                raise NotSubmitted(str(error) if isinstance(error,DevelopmentFault) else
                    'The original link could not be prepared. No Activate was sent.',
                    getattr(error,'code',409),getattr(error,'reason_code',None)) from error
            raise

    async def _start(self):
        from vm_worker import guard
        from sftp import publish_file
        from contracts import digest
        if any((self.owner.work/name).exists() for name in ('link-intent.json','link-request.json','link-activation-intent.json')):
            self.activation_submitted=(self.owner.work/'link-activation-intent.json').exists()
            raise UnconfirmedGuestEffect('This original link operation already has a saved intent. Only its readback is allowed.')
        current=publication(self.store,self.job['binding'],self.deployment,self.job['settings'])
        frozen=self.job['desktopLinkPublication']
        if any(current.get(k)!=frozen.get(k) for k in current): raise NotSubmitted('The own-link publication changed after admission.')
        if frozen.get('vmInvocationId')!=self.owner.intent['vmInvocationId']:
            raise NotSubmitted('The VM service instance changed after the original link preflight.')
        check=lambda:guard(self.store,self.job,self.lease)
        await verify_files(self.ssh,current,self.deployment,check)
        if self.owner.controller_hello.get('desktopLinkVersion')!=1: raise NotSubmitted('The original helper has no native-link-v1 controller.')
        self.original={'schema':1,'executionId':self.owner.intent['executionId'],'jobId':self.job['id'],
            'projectId':self.store.id,'deploymentId':self.deployment['id'],'vmInvocationId':self.owner.intent['vmInvocationId'],
            'publication':frozen,'content':current['content'],'nativePath':current['path'].replace('/C/','C:\\',1).replace('/','\\'),
            'target':self.deployment['guestDirectory']+'\\APP.R4X','createdAt':now()}
        save(self.owner.work/'link-intent.json',self.original)
        value=await self.owner.control.call('link_prepare',linkIntent=self.original['executionId'],
            linkPath=self.original['nativePath'],linkContent=self.original['content'])
        if value.get('result',-1)!=0 or value.get('phase')!=1:
            raise NotSubmitted('Native own-link preparation was not accepted. No Activate was sent.')
        self.prepared=native_receipt(value,self.original,controller=self.owner.controller_hello)
        save(self.owner.work/'link-request.json',{'intent':self.original,'prepared':self.prepared})
        binary=self.owner.work/'LINK.BIN';binary.write_bytes(base64.b64decode(self.prepared['nativeRequest']))
        with binary.open('rb') as stream: os.fsync(stream.fileno())
        guest='/' + self.deployment['guestDirectory'][0]+'/' + self.deployment['guestDirectory'][3:].replace('\\','/')
        await publish_file(self.ssh,binary,guest+'/L'+self.original['executionId'][:7]+'.BIN',digest(binary))
        self.save('prepared',self.prepared);check()
        save(self.owner.work/'link-activation-intent.json',{'requestSha256':digest(binary),'createdAt':now()})
        self.save('activation_unknown')
        activation_born=asyncio.get_running_loop().time()
        self.activation_submitted=True
        value=await self.owner.control.call('link_activate',nativeRequest=self.prepared['nativeRequest'],timeoutSeconds=self.job['settings']['timeoutSeconds'])
        value=native_receipt(value,self.original,self.prepared)
        deadline=activation_born+min(30,self.job['settings']['timeoutSeconds'])
        while not value['processId']:
            self.save(PHASES[value['phase']],value)
            if value['phase'] in (8,9) and value['result']<0: raise NotSubmitted('Native Desktop rejected or expired this original link admission before process start.')
            if value['result'] not in (0,-8) or asyncio.get_running_loop().time()>=deadline:
                raise UnconfirmedGuestEffect('Native link admission has no confirmed process. Read its original request; no activation was repeated.')
            await asyncio.sleep(.2);check()
            value=native_receipt(await self.owner.control.call('link_status',nativeRequest=self.prepared['nativeRequest']),self.original,self.prepared)
        self.process=(value['processId'],value['processGeneration']);self.save(PHASES[value['phase']],value)
        return await self.owner.control.call('poll')

    async def refresh(self):
        if self.prepared is None or asyncio.get_running_loop().time()<self.next_status:return
        self.next_status=asyncio.get_running_loop().time()+.5
        value=native_receipt(await self.owner.control.call('link_status',nativeRequest=self.prepared['nativeRequest']),self.original,self.prepared)
        if self.process and value['processId'] and (value['processId'],value['processGeneration'])!=self.process:
            raise UnconfirmedGuestEffect('The original link operation changed its process generation.')
        self.save(PHASES[value['phase']],value)
        self.status_expired=value['result'] in (-2,-4,-7,-10)

    def settled(self):
        return self.status_expired or self.value is not None and self.value['phase'] in (5,6,7,8,9)

    async def release(self):
        if self.value is not None and self.value.get('phase')==7 and self.value.get('flags',0)&RELEASED:
            return
        value=native_receipt(await self.owner.control.call('link_release',nativeRequest=self.prepared['nativeRequest']),self.original,self.prepared)
        if value['result']!=0 or value['phase']!=7 or value['flags']&RELEASED==0:
            raise UnconfirmedGuestEffect('The original native link cleanup remains unconfirmed.')
        self.save('cleaned',value)
        save(self.owner.work/'link-final.json',{'prepared':self.prepared,'native':value})


def verify_closed(store,job):
    from recovery import read
    work=store.root/'ExecutionWork'/job['id']
    record=read(work/'link-request.json');final=read(work/'link-final.json')
    original=record['intent'];prepared=record['prepared']
    bound_original(store,job,original,read(work/'intent.json'))
    if (original.get('jobId')!=job['id'] or original.get('projectId')!=store.id
            or original.get('deploymentId')!=job['deploymentId'] or original.get('executionId')!=job['executionId']
            or final.get('prepared')!=prepared):
        raise DevelopmentFault('The original native link cleanup binding is inconsistent.')
    result=native_receipt(final['native'],original,prepared)
    if result['result']!=0 or result['phase']!=7 or result['flags']&(ENDED|REAPED|RELEASED)!=(ENDED|REAPED|RELEASED):
        raise DevelopmentFault('The native link cleanup is not fully confirmed.')
    if job.get('process') and (result['processId'],result['processGeneration'])!=(job['process']['instanceId'],job['process']['generation']):
        raise DevelopmentFault('The native link cleanup names another process generation.')


async def recover(store,job,host,vm,lease,info):
    """Read only the saved native request; do not create/adopt a controller."""
    from recovery import read,receipt
    from access import Access,SshTransport
    from deskrun import SSH_EXEC_BYTES
    if not job.get('desktopLinkRequested'):return None
    work=store.root/'ExecutionWork'/job['id']
    if not (work/'link-request.json').exists():return None
    record=read(work/'link-request.json');original=record['intent'];prepared=record['prepared']
    intent=read(work/'intent.json')
    bound_original(store,job,original,intent)
    if (original.get('jobId')!=job['id'] or original.get('projectId')!=store.id or original.get('deploymentId')!=job['deploymentId']
            or original.get('executionId')!=intent.get('executionId') or original.get('vmInvocationId')!=info.get('invocationId')
            or original.get('publication')!=job.get('desktopLinkPublication')):
        raise DevelopmentFault('The original link operation belongs to another execution or VM service instance.')
    native_receipt(prepared,original)
    deployment=store.deployment_metadata(job['deploymentId'])
    if not re.fullmatch(r'[A-Z]:\\Build\\P[A-F0-9]{7}\\D[A-F0-9]{7}',deployment['guestDirectory']):
        raise DevelopmentFault('The original native link recovery path is invalid.')
    command=deployment['guestDirectory']+'\\STHELP.R4X '+original['executionId']+' linkread'
    if len(command.encode())>SSH_EXEC_BYTES:raise DevelopmentFault('The original native link read exceeds the SSH command budget.')
    async with SshTransport(Access(store.projects,store.r4os,None),vm,lease) as ssh:
        transport=await ssh.exec(command,timeout=10,complete=True,limit=12288)
    if transport.get('transportUncertain') or transport.get('exitCode')!=0:
        raise DevelopmentFault('The original native link status is unavailable. No activation was repeated.')
    envelope=json.loads(transport['output'])
    if (envelope.get('version')!=1 or envelope.get('instance')!=original['executionId']
            or envelope.get('sequence')!=0 or envelope.get('success') is not True):
        raise DevelopmentFault('The original native link status envelope is invalid.')
    value=native_receipt(envelope['result'],original,prepared)
    save(work/'link-recovery-observation.json',{'readOnly':True,'native':value,'observedAt':now()})
    return store.recovered(job['id'],'unknown',receipt('native-link-original-readback',guestEndConfirmed=False,
        reason='Original native link status recovered. The original helper closure/output proof is still required; no activation or cleanup was repeated.'),
        desktopLinkActivation={'version':1,'phase':PHASES[value['phase']],'publicationJobId':original['publication']['jobId'],
            'linkPath':original['nativePath'],'linkSha256':original['publication']['sha256'],
            'originalRequestSha256':hashlib.sha256(base64.b64decode(prepared['nativeRequest'])).hexdigest(),
            'native':public(value),'checkedAt':now()})
