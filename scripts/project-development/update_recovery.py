"""Explicit native recovery of the exact latest owned update. No journal surgery."""
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from jobs import now
from layout import save
from update_install import Installation
from update_verify import Observation,correlated
from sysupd_text import parse
from inbox_sftp import InboxSftp,inbox_path
import update_state as state

ACTIONS={'resume':'RESUME','resume-batch':'RESUME-BATCH','abort-batch':'ABORT-BATCH','rollback-last':'ROLLBACK-LAST','cleanup':None}

def permitted(status,record,action):
    value=status['status'];batch=record.get('batchId');transaction=value.get('transactionId')
    own_transaction=transaction in record.get('transactions',[]) or transaction==record.get('lastStatus',{}).get('status',{}).get('transactionId')
    if action=='rollback-last':
        return bool(record.get('installationConfirmed') and correlated(status,record) and status['status']==record['lastStatus']['status'])
    if action=='cleanup':
        if record['phase']=='cleanup_unconfirmed':record={**record,'phase':record['cleanupTerminalPhase']}
        if record['phase'] in ('installed','live_installed'):return correlated(status,record)
        if record['phase']=='rolled_back':return correlated(status,record,'rolled-back')
        return record['phase']=='aborted' and value==record['lastStatus']['status'] and not value['activeOrRecoverable']
    if action=='resume':
        return bool(not batch and own_transaction and transaction in record.get('transactions',[]) and value.get('journalPhase') not in (None,'cleanup','rolled_back') and not value.get('batchPhase') in ('staged','committing','pending-restart','rolling-back'))
    if not batch or value.get('batchId')!=batch:return False
    changed=value!=record.get('lastStatus',{}).get('status')
    own_transition=any(call.get('sent') and call['operation'] in ('COMMIT','RESUME-BATCH','RESUME','ROLLBACK-LAST') for call in record.get('commands',[]))
    if changed and not own_transition:return False
    count=len(record.get('stagedPackageIds',[]))
    progress=value['fields'].get('batch-progress',value['fields'].get('progress'))
    if not progress or int(progress.split('/')[1])!=count:return False
    if action=='abort-batch':
        return value.get('batchPhase') in ('staged','verifying','staging') and value.get('journalPhase') in (None,'cleanup','rolled_back')
    if action=='resume-batch':
        return value.get('batchPhase') in ('staged','verifying','staging','committing','pending-restart','failed','rolling-back','installed','rolled-back')
    return False

async def recover_live_identity(ssh,status,record,guard):
    native=status['status']
    if record.get('batchId') or record.get('transactions') or native.get('mode')!='journal' or native.get('batchPhase') in ('staged','committing','pending-restart','rolling-back'):
        return False
    if not native.get('transactionId') or native['transactionId']==record.get('lastStatus',{}).get('status',{}).get('transactionId'):return False
    source=native['fields'].get('source')
    for item in record['packages']:
        transfer=item['transfer'];package=item['package'];metadata=package['plan']['metadata']
        sent=any(call.get('sent') and call['operation']=='STAGE' and call['command']=='SYSUPD STAGE '+transfer['guestPath'] for call in record['commands'])
        if (not sent or source!=transfer['guestPath'] or native['fields'].get('package-version')!=metadata['packageVersion']
            or native['fields'].get('release')!=metadata['targetRelease'] or native['fields'].get('components')!=str(len(package['plan']['payloads']))):continue
        async with InboxSftp(ssh,guard) as client:
            observed=await client.get_hash(inbox_path(transfer['final'],'R4U'),package['bytes'])
        if client.exit_code!=0 or not observed or any(observed[key]!=package[key] for key in ('bytes','sha256')):
            raise DevelopmentFault('The original live recovery source no longer matches its immutable package.')
        record['transactions']=[native['transactionId']]
        record['identityRecovery']={'nativeStatus':status,'packageArtifactId':package['id'],'sha256':package['sha256'],'fullSourceReadVerified':True,'originalStageIntentMatched':True}
        record['lastStatus']=status
        return True
    return False


class Recovery(Installation):
    async def run(self):
        from queue_lease import reserve
        from access import Access,SshTransport
        from vm_worker import broker_call,guard
        vm=self.job['binding'];action=self.job['recoveryAction']
        self.value=state.read(self.store,self.job['updateId'],current=True)
        if self.value['revision']!=self.job['updateRevision']:raise DevelopmentFault('The reviewed recovery record changed.')
        scope={'kind':'job','projectId':self.store.id,'projectRevision':self.job['projectRevision'],'jobId':self.job['id'],
            'vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256']}
        async with reserve(self.store,self.job,scope) as lease:
            self.lease=lease
            target=await broker_call({'operation':'bind_update_target','projectId':self.store.id,'jobId':self.job['id'],'leaseId':lease.id,'token':lease.token})
            scope['bootId']=target['bootId'];save(lease.root/'leases'/(lease.id+'.json'),lease.value)
            access=Access(self.store.projects,self.store.r4os,None)
            if access.record(vm['id']).get('hostKeyFingerprint')!=self.value.get('hostKeyFingerprint'):raise DevelopmentFault('Original update SSH identity changed; no recovery command was issued.')
            async with SshTransport(access,vm,lease) as ssh:
                status=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
                if action=='resume' and await recover_live_identity(ssh,status,self.value,lambda:guard(self.store,self.job,lease)):
                    self.persist()
                if not permitted(status,self.value,action):raise DevelopmentFault('Fresh native state is not the exact own eligible recovery/last-update state. Preserve foreign or changed state.')
                if action=='cleanup':return await self.cleanup(ssh,status)
                self.value.setdefault('recoveryJobIds',[]).append(self.job['id'])
                self.value['recoveryIntent']={'jobId':self.job['id'],'action':action,'beforeStatus':status,'at':now(),'rebootAuthorized':self.job['confirmReboot']}
                if action=='rollback-last':
                    self.value['rollbackTransactionId']=status['status'].get('transactionId')
                    self.value['previousInstallationProof']=self.value.get('proof')
                self.value['phase']='recovering';self.value['installationConfirmed']=False;self.persist()
                try:reply=await self.command(ssh,ACTIONS[action],mutating=True)
                except UnconfirmedGuestEffect as error:
                    self.value['recoveryTransportError']=str(error);self.persist();reply=None
                if action=='abort-batch':
                    after=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
                    if not reply or not reply['success'] or after['status'].get('batchId')==self.value['batchId'] or after['status']['activeOrRecoverable']:
                        raise UnconfirmedGuestEffect('Native ABORT-BATCH has no positive owned terminal proof. Do not repeat it.')
                    self.value.update(phase='aborted',lastStatus=after,abortConfirmed=True,installationConfirmed=False);self.persist()
                    return self.store.update(self.job['id'],'completed',phase='aborted',exitCode=0)
            # Includes actual COMMIT replies from RESUME-BATCH on a prepared batch.
            return await Observation(self.store,self.job,self.value).in_lease(lease)

    async def cleanup(self,ssh,status):
        from vm_worker import guard
        terminal=self.value.get('cleanupTerminalPhase',self.value['phase']);self.value.setdefault('cleanupIntents',[])
        self.value['cleanupJobId']=self.job['id'];self.persist()
        try:
            async with InboxSftp(ssh,lambda:guard(self.store,self.job,self.lease)) as client:
                for item in self.value['packages']:
                    transfer=item['transfer'];package=item['package']
                    for key in ('tmp','final'):
                        path=inbox_path(transfer[key],'TMP' if key=='tmp' else 'R4U')
                        observed=await client.get_hash(path,134217728)
                        if observed is None:
                            self.value.setdefault('cleanupObservations',[]).append({'path':path,'absent':True});self.persist();continue
                        if any(observed[field]!=package[field] for field in ('bytes','sha256')):
                            self.value.setdefault('cleanupObservations',[]).append({'path':path,'preserved':True,'reason':'Different or partial bytes are not eligible for removal.'});self.persist();continue
                        # No native writer state may change between authorization and removal.
                        current=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
                        if current['status']!=status['status'] or not permitted(current,self.value,'cleanup'):raise DevelopmentFault('Native state changed; preserve transport material.')
                        intent={'path':path,'sha256':package['sha256'],'bytes':package['bytes'],'sent':True,'at':now()}
                        self.value['cleanupIntents'].append(intent);self.persist()
                        await client.remove(path);intent['acknowledged']=True;self.persist()
                        if await client.stat(path) is not None:raise UnconfirmedGuestEffect('Original transport removal remains unconfirmed.')
            self.value['cleanupTransport']={'events':getattr(client,'events',[]),'requestCounts':getattr(client,'counts',{}),'sshExitCode':client.exit_code,'stderr':getattr(client,'stderr',b'').decode('utf8',errors='replace')}
            if client.exit_code!=0:raise UnconfirmedGuestEffect('Transport cleanup session ended without a confirmed close.')
            self.value.update(phase=terminal,cleanupConfirmed=True);self.persist()
            return self.store.update(self.job['id'],'completed',phase='transport_cleanup_complete',exitCode=0)
        except BaseException as error:
            if 'client' in locals():
                self.value['cleanupTransport']={'events':getattr(client,'events',[]),'requestCounts':getattr(client,'counts',{}),'sshExitCode':client.exit_code,'stderr':getattr(client,'stderr',b'').decode('utf8',errors='replace')}
            self.value.update(phase='cleanup_unconfirmed',cleanupTerminalPhase=terminal,error=str(error));self.persist()
            raise UnconfirmedGuestEffect('Original transport cleanup is unconfirmed. Inspect only the recorded paths; no REMOVE was repeated.') from error

async def reconcile(store,job,host):
    """Original unknown jobs get receipts; native writes are never replayed here."""
    from recovery import receipt
    value=state.read(store,job['updateId'])
    if value['phase']!='cleanup_unconfirmed':
        confirmed=((value['phase'] in ('installed','live_installed') and value.get('installationConfirmed') and value.get('proof'))
            or (value['phase']=='rolled_back' and value.get('rollbackConfirmed')) or (value['phase']=='aborted' and value.get('abortConfirmed')))
        requested=(job.get('recoveryAction')=='rollback-last' and value.get('rollbackConfirmed')) or (job.get('recoveryAction')=='abort-batch' and value.get('abortConfirmed'))
        outcome='completed' if value.get('installationConfirmed') or requested else 'interrupted'
        return store.recovered(job['id'],outcome if confirmed else 'unknown',
            receipt('owned-native-update-history',historical=True,nativeWritesReplayed=False,terminalConfirmed=bool(confirmed)),
            updateInstallation=value,error=None if confirmed else 'Current native proof is required. Use a new read-only verification or explicitly authorized recovery action for this same update ID.')
    value=state.read(store,job['updateId'],current=True)
    if value.get('cleanupJobId')!=job['id']:raise DevelopmentFault('The original cleanup effect belongs to another job.')
    from access import Access,SshTransport,vm_config
    from lease import VmLease,inspect
    from vm_client import vm_call
    vm=vm_config(store.r4os,value['vmId'])
    if (store.project['vmId']!=vm['id'] or value['vmRevision']!=vm['revision'] or value['imageSha256']!=vm['imageSha256'] or value.get('systemGeneration')!=vm.get('systemGeneration')):
        raise DevelopmentFault('The original cleanup VM/system binding changed.')
    eligible={item['transfer'][key] for item in value['packages'] for key in ('tmp','final')}
    paths=[intent['path'] for intent in value['cleanupIntents']]
    if any(path not in eligible for path in paths):raise DevelopmentFault('A cleanup intent is outside its original transport pairs.')
    scope={'kind':'recovery','vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256']}
    with VmLease(store.projects,vm['id'],scope) as lease:
        info=await vm_call(lease,'info')
        if info['vm']['state']!='running':raise DevelopmentFault('Explicitly start the original VM before cleanup observation.')
        boot=await host.boots.ensure(vm,info['invocationId']);scope['bootId']=boot['bootId'];save(lease.root/'leases'/(lease.id+'.json'),lease.value)
        access=Access(store.projects,store.r4os,None)
        if access.record(vm['id']).get('hostKeyFingerprint')!=value.get('hostKeyFingerprint'):raise DevelopmentFault('Original cleanup SSH identity changed.')
        async with SshTransport(access,vm,lease) as ssh:
            observed=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
            prospective={**value,'phase':value['cleanupTerminalPhase']}
            if not permitted(observed,prospective,'cleanup'):raise DevelopmentFault('Native ownership/terminal state changed. Preserve transport material.')
            async with InboxSftp(ssh,lambda:inspect(store.projects,lease.id,lease.token)) as client:
                present=[path for path in paths if await client.stat(inbox_path(path)) is not None]
            if client.exit_code!=0:raise DevelopmentFault('The original cleanup paths were not read completely.')
    if present:
        return store.recovered(job['id'],'unknown',receipt('own-cleanup-known-paths',readOnly=True,absent=False),
            error='An original cleanup path is still present. No REMOVE was repeated. Preserve its bytes for explicit inspection.')
    value.update(phase=value['cleanupTerminalPhase'],cleanupConfirmed=True,cleanupReconciledAt=now())
    value=state.write(store,value)
    return store.recovered(job['id'],'completed',receipt('own-cleanup-known-paths',readOnly=True,absent=True),
        updateInstallation=value,error=None,exitCode=0)
