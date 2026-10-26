"""Native VERIFY/STAGE, including effective live APPLY, and separately confirmed COMMIT."""
import asyncio
from pathlib import Path
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from jobs import folder,now
from layout import save
from inbox_sftp import InboxSftp,inbox_path
from update_probe import Probe
from sysupd_text import parse,inventory
import update_state as state

def check_reply(reply,package,operation):
    fields=reply.get('fields',{});meta=package['plan']['metadata']
    if not reply['success'] or fields.get('package')!=meta['packageId'] or fields.get('release')!=meta['targetRelease']:
        raise DevelopmentFault('Native '+operation+' did not positively confirm this exact package/release.')
    if fields.get('package-version',meta['packageVersion'])!=meta['packageVersion']:
        raise DevelopmentFault('Native package version differs from the frozen plan.')
    if operation=='VERIFY':
        if fields.get('payloads')!=str(len(package['plan']['payloads'])) or fields.get('components')!=str(len(package['plan']['payloads'])) or fields.get('requires')!=str(len(package['plan']['requirements'])):
            raise DevelopmentFault('Native VERIFY component/requirement counts differ from the frozen package.')

def component_proof(data,packages):
    found=[]
    for package in packages:
        for payload in package['plan']['payloads']:
            component=payload['component']
            hits=[item for item in data['entries'] if item['kind']==component['kind'] and item['name'].casefold()==component['name'].casefold() and item['target'].replace(chr(92),'/').casefold()==component['target'].casefold() and item['version']==component['version']]
            if len(hits)!=1:raise DevelopmentFault('Installed inventory does not confirm every exact native component.')
            found.append(hits[0])
    return found

async def full_inventory(ssh,work,prefix):
    from sftp import download_update_metadata
    reads=[]
    for suffix in ('first','second'):
        reads.append(await download_update_metadata(ssh,'inventory',work/(prefix+'-'+suffix+'.json')))
    if reads[0]['sha256']!=reads[1]['sha256'] or reads[0]['bytes']!=reads[1]['bytes']:raise DevelopmentFault('Installed inventory changed during complete reads.')
    return inventory((work/(prefix+'-first.json')).read_text()),reads

async def capture_previous(ssh,packages,guard):
    from installed_sftp import InstalledRead
    payloads=[payload for package in packages for payload in package['plan']['payloads']]
    result=[];remaining=134217728
    async with InstalledRead(ssh,payloads,guard) as reader:
        for payload in payloads:
            received=await reader.get_hash('/C'+payload['canonicalTarget'],remaining)
            if received:remaining-=received['bytes']
            result.append({'target':payload['canonicalTarget'],'file':received})
    if reader.exit_code!=0:raise DevelopmentFault('The pre-install artifact snapshot did not close cleanly.')
    return result


class Installation:
    def __init__(self,store,job):
        self.store,self.job=store,job;self.work=folder(store.root/'UpdateWork'/job['id']);self.value=None
    def persist(self):
        self.value=state.write(self.store,self.value);self.store.update(self.job['id'],updateInstallation=self.value)
    async def command(self,ssh,operation,path=None,mutating=False):
        from vm_worker import guard
        guard(self.store,self.job,self.lease)
        command='SYSUPD '+operation+(' '+path if path else '')
        key=str(len(self.value['commands']))
        call={'id':key,'jobId':self.job['id'],'operation':operation,'command':command,'intentAt':now(),'mutating':mutating,'sent':False}
        self.value['commands'].append(call);self.persist()
        call=self.value['commands'][-1];call['sent']=True;self.persist()
        if mutating:
            from update_epoch import invalidate
            self.value['updateEpoch']=invalidate(self.store,self.value,operation);self.persist()
        try:
            captured=await ssh.exec(command,timeout=90 if operation=='STAGE' else 30,complete=True,limit=131072)
            save(self.work/('command-'+key+'.json'),captured)
            call['capture']={key:value for key,value in captured.items() if key!='output'}
            for channel in ('stdout','stderr'):
                if len(call['capture'].get(channel,'').encode())>8192:
                    call['capture'][channel]=call['capture'][channel].encode()[:8192].decode('utf8',errors='replace')
                    call['capture']['displayTruncated']=True
            self.persist()
            reply=parse(operation,captured);call['reply']=reply;self.persist()
            if mutating and not reply['confirmed']:raise UnconfirmedGuestEffect('The native '+operation+' acknowledgement is unconfirmed; the original intent must be reconciled without replay.')
            return reply
        except BaseException as error:
            if mutating:
                self.value['phase']='recovery_required';self.value['error']='Native '+operation+' has a durable intent; inspect its preserved response before further action.';self.persist()
                raise UnconfirmedGuestEffect(self.value['error']) from error
            raise
    async def run(self):
        return await Probe(self.store,self.job).run(after_ready=self.stage)
    async def stage(self,lease,target,observation):
        from access import Access,SshTransport
        from update_jobs import transfers
        from vm_worker import guard
        self.lease=lease;state.idle(self.store.projects,target['vmId'])
        items=transfers(self.store,[item['jobId'] for item in self.job['updateTransfers']],self.job['binding'])
        if any(item['transfer'].get('hostKeyFingerprint')!=observation['hostKeyFingerprint'] for item in items):
            raise DevelopmentFault('The original Inbox SSH host-key binding changed. Verify identity and create a new explicit transfer.')
        packages=[item['package'] for item in items]
        self.value={'schema':1,'id':self.job['updateId'],'projectId':self.store.id,'jobId':self.job['id'],'sessionId':self.job.get('sessionId'),'agentRunId':self.job.get('agentRunId'),'revision':0,
            **{key:target[key] for key in ('vmId','vmRevision','imageId','imageSha256','systemGeneration')},
            'sourceBootId':target['bootId'],'targetRelease':packages[0]['plan']['metadata']['targetRelease'],
            'packageArtifactIds':[item['id'] for item in packages],'transferJobIds':[item['jobId'] for item in items],
            'phase':'verifying','createdAt':now(),'commands':[],'packages':items,'lastStatus':observation['status'],'transactions':[],
            'hostKeyFingerprint':observation['hostKeyFingerprint'],'externalWriterLock':False}
        self.persist()
        try:
            access=Access(self.store.projects,self.store.r4os,None)
            async with SshTransport(access,self.job['binding'],lease) as ssh:
                # Public VERIFY against the actual installed state for every package before any STAGE.
                for item in items:
                    path=inbox_path(item['transfer']['final'],'R4U')
                    async with InboxSftp(ssh,lambda:guard(self.store,self.job,lease)) as client:
                        received=await client.get_hash(path,item['package']['bytes'])
                    if client.exit_code!=0 or not received or any(received[k]!=item['package'][k] for k in ('bytes','sha256')):
                        raise DevelopmentFault('The complete published Inbox package differs. No native STAGE was issued.')
                    check_reply(await self.command(ssh,'VERIFY',item['transfer']['guestPath']),item['package'],'VERIFY')
                from vm_worker import guard
                self.value['previousFiles']=await capture_previous(ssh,packages,lambda:guard(self.store,self.job,lease))
                self.persist()
                for index,item in enumerate(items):
                    status=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
                    if not state.matches(status,self.value):raise DevelopmentFault('Native update ownership/state changed before STAGE.')
                    # Repeat public VERIFY immediately before this mutating call; never invent VERIFY-BATCH.
                    check_reply(await self.command(ssh,'VERIFY',item['transfer']['guestPath']),item['package'],'VERIFY')
                    self.value['phase']='staging';self.persist()
                    reply=await self.command(ssh,'STAGE',item['transfer']['guestPath'],mutating=True)
                    check_reply(reply,item['package'],'STAGE')
                    status=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072));native=status['status']
                    if reply['effectiveOperation']=='APPLY':
                        transaction=reply['fields'].get('transaction')
                        if (not transaction or native.get('transactionId')!=transaction or native.get('journalPhase')!='cleanup' or native['activeOrRecoverable']
                            or reply['fields'].get('reboot')!='no'):
                            raise UnconfirmedGuestEffect('Live APPLY has no matching terminal transaction proof.')
                        self.value['transactions'].append(transaction)
                        data,reads=await full_inventory(ssh,self.work,'live-'+str(index))
                        proof=component_proof(data,[item['package']]);self.value.setdefault('liveProofs',[]).append({'transactionId':transaction,'components':proof,'inventoryReads':reads})
                    else:
                        batch=reply['fields'].get('batch')
                        if (not batch or native.get('batchId')!=batch or native.get('batchPhase')!='staged'
                                or self.value.get('batchId',batch)!=batch or (native['mode']=='batch' and native['fields']['release']!=self.value['targetRelease'])):
                            raise UnconfirmedGuestEffect('STAGE has no matching owned staged batch.')
                        count=len(self.value.get('stagedPackageIds',[]))+1
                        if reply['fields'].get('packages')!=str(count):raise UnconfirmedGuestEffect('Native batch package count differs from the explicit owned plan.')
                        self.value['batchId']=batch;self.value.setdefault('stagedPackageIds',[]).append(item['package']['id'])
                    self.value['lastStatus']=status;self.persist()
                self.value['phase']='awaiting_commit' if self.value.get('batchId') else 'live_installed'
                self.value['installationConfirmed']=not bool(self.value.get('batchId'));self.persist()
            if self.value['phase']=='live_installed':
                from update_verify import Observation
                return await Observation(self.store,self.job,self.value).in_lease(lease)
            return self.store.update(self.job['id'],'completed',phase=self.value['phase'],exitCode=0)
        except BaseException as error:
            # A nested observation can have newer attempts/proof; preserve its current record.
            self.value=state.read(self.store,self.value['id'],current=True)
            if any(call['mutating'] and call['sent'] for call in self.value['commands']):
                self.value['phase']='recovery_required';self.value['error']=str(error);self.persist()
                raise UnconfirmedGuestEffect('This native installation has an original STAGE intent. Preserve its state and use explicit recovery; no native write was retried.') from error
            self.value['phase']='rejected';self.value['error']=str(error);self.persist();raise

class Commit(Installation):
    async def run(self):
        from access import Access,SshTransport
        from queue_lease import reserve
        from vm_worker import broker_call
        record=state.read(self.store,self.job['updateId'],current=True)
        if record['revision']!=self.job['updateRevision'] or record['phase']!='awaiting_commit':raise DevelopmentFault('The reviewed commit record changed.')
        vm=self.job['binding']
        scope={'kind':'job','projectId':self.store.id,'projectRevision':self.job['projectRevision'],'jobId':self.job['id'],
            'vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256']}
        async with reserve(self.store,self.job,scope) as lease:
            self.lease=lease
            target=await broker_call({'operation':'bind_update_target','projectId':self.store.id,'jobId':self.job['id'],'leaseId':lease.id,'token':lease.token})
            scope['bootId']=target['bootId'];save(lease.root/'leases'/(lease.id+'.json'),lease.value)
            self.value=state.read(self.store,self.job['updateId'],current=True)
            if self.value['revision']!=self.job['updateRevision']:raise DevelopmentFault('The owned update changed while waiting for its VM.')
            access=Access(self.store.projects,self.store.r4os,None)
            if access.record(vm['id']).get('hostKeyFingerprint')!=self.value.get('hostKeyFingerprint'):
                raise DevelopmentFault('The original SSH host-key binding changed. No COMMIT was sent.')
            async with SshTransport(access,vm,lease) as ssh:
                status=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
                if not state.matches(status,self.value) or status['status'].get('batchPhase')!='staged':raise DevelopmentFault('The fresh native batch differs from the confirmed commit action.')
                self.value.update(phase='commit_intent',commitJobId=self.job['id'],commitBootId=target['bootId'],rebootAuthorized=True);self.persist()
                try:
                    reply=await self.command(ssh,'COMMIT',mutating=True)
                    if not reply['success'] or reply['fields'].get('batch')!=self.value['batchId'] or reply['fields'].get('release')!=self.value['targetRelease']:
                        raise UnconfirmedGuestEffect('The original COMMIT has no exact positive batch acknowledgement.')
                    self.value['commitReply']=reply
                except UnconfirmedGuestEffect as error:
                    self.value['commitTransportError']=str(error)
                self.value['phase']='reconnecting';self.persist()
            from update_verify import Observation
            return await Observation(self.store,self.job,self.value).in_lease(lease)
