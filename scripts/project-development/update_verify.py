"""Bounded read-only post-install observation. Never repeat COMMIT or invoke RESUME."""
import asyncio
from contracts import DevelopmentFault,UnconfirmedGuestEffect
from jobs import folder,now
from layout import save
from sysupd_text import parse,release_file
from update_install import component_proof,full_inventory
from installed_sftp import InstalledRead
import update_state as state

def correlated(status,record):
    value=status['status']
    if value['fields'].get('release')!=record['targetRelease']:return False
    if record.get('batchId'):
        return (value.get('batchId')==record['batchId'] and value.get('batchPhase')=='installed'
                and value.get('journalPhase','cleanup')=='cleanup' and not value['activeOrRecoverable'])
    return bool(record.get('transactions') and value.get('transactionId')==record['transactions'][-1]
                and value.get('journalPhase')=='cleanup' and not value['activeOrRecoverable'])

class Observation:
    def __init__(self,store,job,record,seconds=120,hashes=True):
        self.store,self.job,self.value=store,job,record;self.seconds=seconds;self.hashes=hashes
        self.work=folder(store.root/'UpdateVerifyWork'/job['id'])
    def persist(self):
        self.value=state.write(self.store,self.value);self.store.update(self.job['id'],updateInstallation=self.value)
    async def run(self):
        from queue_lease import reserve
        vm=self.job['binding']
        scope={'kind':'job','projectId':self.store.id,'projectRevision':self.job['projectRevision'],'jobId':self.job['id'],
            'vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256']}
        async with reserve(self.store,self.job,scope) as lease:return await self.in_lease(lease)
    async def in_lease(self,lease):
        try:return await asyncio.wait_for(self.observe(lease),self.seconds)
        except BaseException as error:
            self.value.update(phase='recovery_required',installationConfirmed=False,error='The bounded native update observation ended without a correlated terminal proof. No command was replayed. '+str(error)[:1000])
            self.persist();raise UnconfirmedGuestEffect(self.value['error']) from error
    async def observe(self,lease):
        from access import Access,SshTransport,guest_version
        from vm_worker import guard,broker_call
        from package_jobs import artifact
        access=Access(self.store.projects,self.store.r4os,None);vm=self.job['binding']
        expected=self.value.get('hostKeyFingerprint')
        if not expected or access.record(vm['id']).get('hostKeyFingerprint')!=expected:
            raise DevelopmentFault('The original SSH host-key binding changed. Explicit identity review is required.')
        packages=[artifact(self.store,ident) for ident in self.value['packageArtifactIds']]
        if packages!=[item['package'] for item in self.value['packages']]:raise DevelopmentFault('The original package receipts changed.')
        # A native reboot invalidates the previous boot lease; clear it before read-only rebinding.
        lease.scope.pop('bootId',None);save(lease.root/'leases'/(lease.id+'.json'),lease.value)
        self.value['phase']='reconciling';self.persist()
        attempt=0
        while True:
            guard(self.store,self.job)
            attempt+=1;entry={'attempt':attempt,'at':now()}
            try:
                target=await broker_call({'operation':'bind_update_target','projectId':self.store.id,'jobId':self.job['id'],'leaseId':lease.id,'token':lease.token})
                # No old boot is accepted across a pending reset. Each attempt binds a current QMP observation.
                lease.scope['bootId']=target['bootId'];save(lease.root/'leases'/(lease.id+'.json'),lease.value)
                async with SshTransport(access,vm,lease) as ssh:
                    captured=await ssh.exec('SYSUPD STATUS',timeout=8,complete=True,limit=131072)
                    save(self.work/('status-'+str(attempt)+'.json'),captured)
                    if any(text in captured.get('stderr','') for text in ('HOST IDENTIFICATION HAS CHANGED','Host key verification failed','Permission denied')):
                        raise DevelopmentFault('The guest rejected the original SSH identity; automatic trust is forbidden.',403)
                    status=parse('STATUS',captured)
                    entry['status']=status
                    if not correlated(status,self.value):
                        own=status['status']
                        if self.value.get('batchId') and own.get('batchId') not in (None,self.value['batchId']):
                            raise DevelopmentFault('A different native batch is current. Preserve the original update evidence.',403)
                        if not self.value.get('batchId') and own.get('transactionId') and own.get('transactionId') not in self.value.get('transactions',[]):
                            raise DevelopmentFault('A newer unowned transaction blocks this installation proof.',403)
                        self.value['lastObservedStatus']=status
                    else:
                        guard(self.store,self.job,lease)
                        ver=await ssh.exec('VER',timeout=8,complete=True,limit=131072);version=guest_version(ver)
                        version_capture=await ssh.exec(r'TYPE C:\R4OS\CONFIG\VERSION.R4S',timeout=8,complete=True,limit=4096)
                        if version_capture['exitCode']!=0 or version_capture.get('truncated') or version_capture.get('transportUncertain'):raise DevelopmentFault('Installed release observation is incomplete.')
                        visible_release=release_file(version_capture['stdout'])
                        if self.value.get('batchId') and visible_release!=self.value['targetRelease']:raise DevelopmentFault('The reboot batch has no matching installed release file.')
                        data,reads=await full_inventory(ssh,self.work,'attempt-'+str(attempt))
                        components=component_proof(data,packages);files=[]
                        if self.hashes:
                            payloads=[payload for package in packages for payload in package['plan']['payloads']]
                            async with InstalledRead(ssh,payloads,lambda:guard(self.store,self.job,lease)) as reader:
                                for payload in payloads:
                                    path='/C'+payload['canonicalTarget'];observed=await reader.get_hash(path,payload['file']['bytes'])
                                    if not observed or any(observed[key]!=payload['file'][key] for key in ('bytes','sha256')):
                                        raise DevelopmentFault('An installed artifact differs from its original package bytes.')
                                    files.append({'target':payload['canonicalTarget'],**observed})
                            if reader.exit_code!=0:raise DevelopmentFault('Installed artifact readback did not close cleanly.')
                        final=parse('STATUS',await ssh.exec('SYSUPD STATUS',timeout=8,complete=True,limit=131072))
                        if final['status']!=status['status'] or not correlated(final,self.value):raise DevelopmentFault('Native state changed during installation proof.')
                        ssh.publish_host_key()
                        if access.record(vm['id']).get('hostKeyFingerprint')!=expected:raise DevelopmentFault('The original host key was not preserved.',403)
                        if not self.value.get('updateEpoch'):
                            from update_epoch import invalidate
                            self.value['updateEpoch']=invalidate(self.store,self.value,'confirmed-installed-update')
                        self.value.update(phase='installed' if self.value.get('batchId') else 'live_installed',installationConfirmed=True,
                            lastStatus=final,proof={'confirmedAt':now(),'target':target,'components':components,'inventoryReads':reads,
                            'fullArtifactHashesRequested':self.hashes,'files':files,'installedRelease':visible_release,'activeKernel':version['kernel'],
                            'readOnly':True,'nativeServiceMayHaveFinalized':True,'commitNotRepeated':True,'resumeNotIssued':True})
                        self.persist()
                        record=access.record(vm['id']);record.pop('lastError',None);record['readiness']={'checkedAt':now(),'vmRevision':vm['revision'],'bootId':target['bootId'],**version};access.save_record(vm['id'],record)
                        return self.store.update(self.job['id'],'completed',phase=self.value['phase'],exitCode=0)
            except (DevelopmentFault,OSError) as error:
                if getattr(error,'code',None)==403:
                    self.value.update(phase='recovery_required',error=str(error),installationConfirmed=False);self.persist();raise
                entry['error']=str(error)[:1000]
            self.value['observationAttempts']=(self.value.get('observationAttempts',[])+[entry])[-16:]
            self.value['observationAttemptCount']=attempt;self.persist()
            lease.scope.pop('bootId',None);save(lease.root/'leases'/(lease.id+'.json'),lease.value)
            await asyncio.sleep(min(3,.5*attempt))
