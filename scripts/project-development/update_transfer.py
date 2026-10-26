"""Create-only Inbox publication. Every write boundary has an original durable intent."""
import asyncio
import os
from pathlib import Path
import shutil
import stat
import uuid
from contracts import DevelopmentFault, UnconfirmedGuestEffect, digest, LIMITS
from jobs import folder, now
from layout import save
from package_jobs import artifact
from update_probe import Probe
from inbox_sftp import InboxSftp, PREFIX
from sysupd_text import parse, may_upload


class Transfer:
    def __init__(self, store, job):
        self.store,self.job=store,job;self.work=folder(store.root/'UpdateTransferWork'/job['id'])
        self.package=job['updatePackage'];self.frozen=self.work/'package.R4U'
        self.value={'schema':1,'jobId':job['id'],'projectId':store.id,'packageArtifactId':self.package['id'],
            'sha256':self.package['sha256'],'bytes':self.package['bytes'],'phase':'preparing','published':False,'createdAt':now(),'collisions':[]}

    def persist(self):
        save(self.work/'transport.json',self.value)
        self.store.update(self.job['id'],updateTransfer=self.value)

    def freeze(self):
        if self.frozen.exists() or self.frozen.is_symlink() or (self.work/'transport.json').exists():
            raise DevelopmentFault('This transfer already has private work. Its writes were not replayed.')
        package=artifact(self.store,self.package['id'])
        if package!=self.package:raise DevelopmentFault('The accepted immutable package receipt changed.')
        if shutil.disk_usage(self.work).free < package['bytes']*2+64*1024*1024:
            raise DevelopmentFault('Insufficient local space for the bounded transfer and its readback.')
        source=self.store.root/'UpdatePackages'/package['id']/'package.R4U'
        with source.open('rb') as src,self.frozen.open('xb') as target:
            shutil.copyfileobj(src,target,65536);target.flush();os.fsync(target.fileno())
        self.frozen.chmod(0o400)
        if digest(self.frozen)!=self.value['sha256'] or self.frozen.stat().st_size!=self.value['bytes']:
            raise DevelopmentFault('The local package changed while freezing the Inbox transfer.')
        self.persist()

    async def run(self):
        self.freeze()
        try:
            return await Probe(self.store,self.job).run(after_ready=self.publish)
        except (asyncio.CancelledError, TimeoutError) as error:
            if self.value.get('reservationObservedEmpty'):
                raise UnconfirmedGuestEffect('The transfer stopped after a durable Inbox write intent. Inspect its original paths without repeating writes.') from error
            raise

    async def publish(self,lease,target,observation):
        from access import Access,SshTransport
        from vm_worker import guard
        vm=self.job['binding'];access=Access(self.store.projects,self.store.r4os,None)
        check=lambda:guard(self.store,self.job,lease)
        self.value['target']=target;self.value['hostKeyFingerprint']=observation['hostKeyFingerprint'];self.persist()
        async with SshTransport(access,vm,lease) as ssh:
            fresh=parse('STATUS',await ssh.exec('SYSUPD STATUS',complete=True,limit=131072))
            if not may_upload(fresh) or fresh['status']!=observation['status']['status']:
                raise DevelopmentFault('Native update state changed before Inbox transfer.')
            async with InboxSftp(ssh,check) as client:
                for attempt in range(8):
                    base='U'+uuid.uuid4().hex[:7].upper()
                    self.value.update(tmp=PREFIX+base+'.TMP',final=PREFIX+base+'.R4U',phase='reserving')
                    self.persist()
                    old_tmp=await client.stat(self.value['tmp']);old_final=await client.stat(self.value['final'])
                    if old_tmp is None and old_final is None:break
                    self.value['collisions'].append({'tmp':self.value['tmp'],'final':self.value['final'],'tmpExisted':old_tmp is not None,'finalExisted':old_final is not None})
                else:raise DevelopmentFault('No unused short Inbox name could be reserved. Existing files were preserved.')
                self.value.update(phase='upload_intent',reservationObservedEmpty=True,acknowledgedBytes=0);self.persist()
                last=0
                def progress(value):
                    nonlocal last
                    self.value['acknowledgedBytes']=value
                    if value-last>=1024*1024 or value==self.value['bytes']:
                        last=value;self.persist()
                def closing():
                    self.value['phase']='close_intent';self.persist()
                self.store.update(self.job['id'],phase='uploading_inbox')
                uploaded=await client.put(self.value['tmp'],self.frozen,self.value,progress,closing)
                self.value.update(phase='uploaded',upload=uploaded);self.persist()
                check();self.store.update(self.job['id'],phase='checking_inbox_hash')
                readback=await client.get_hash(self.value['tmp'],self.value['bytes'])
                self.value['readback']=readback;self.persist()
                if not readback or readback['bytes']!=self.value['bytes'] or readback['sha256']!=self.value['sha256']:
                    self.value['phase']='readback_mismatch';self.persist()
                    raise DevelopmentFault('Full Inbox readback size/SHA-256 differs. No R4U publication or native verification was authorized.')
                if artifact(self.store,self.package['id'])!=self.package or digest(self.frozen)!=self.value['sha256']:
                    raise DevelopmentFault('The frozen package changed before publication.')
                if await client.stat(self.value['final']) is not None:
                    self.value['phase']='publication_collision';self.persist()
                    raise DevelopmentFault('The final Inbox name now exists. Neither file was overwritten.')
                check();self.value.update(phase='rename_intent',renameIntent=True);self.persist()
                self.store.update(self.job['id'],phase='publishing_inbox')
                await client.rename(self.value['tmp'],self.value['final'])
                self.value.update(renameAcknowledged=True,phase='rename_acknowledged');self.persist()
                final=await client.get_hash(self.value['final'],self.value['bytes'])
                remaining=await client.stat(self.value['tmp'])
                if (not final or final['bytes']!=self.value['bytes'] or final['sha256']!=self.value['sha256'] or remaining is not None):
                    raise UnconfirmedGuestEffect('The recorded Inbox publication changed or remains ambiguous. Inspect only its recorded paths.')
                self.value.update(finalRead=final,events=client.events,requestCounts=client.counts)
            self.value.update(sshExitCode=client.exit_code,stderr=client.stderr.decode('utf8',errors='replace'))
            self.persist()
            if client.exit_code!=0:
                raise UnconfirmedGuestEffect('The Inbox SFTP session ended without clean completion. Read the original paths before any further write.')
            check()
            self.value.update(phase='published',published=True,guestPath='C:'+self.value['final'][2:].replace('/',chr(92)),completedAt=now())
            self.persist()
            with (self.store.evidence(self.job['id'])/'output.log').open('ab') as log:
                log.write(('Inbox published: '+self.value['guestPath']+'\nFull readback SHA-256: '+self.value['sha256']+'\nNo SYSUPD VERIFY/STAGE or installation was issued.\n').encode())
            return self.store.update(self.job['id'],'completed',phase='inbox_published',exitCode=0)


async def reconcile(store,job,host):
    """Read-only resolution of the original names, never OPEN-write/CLOSE-write/RENAME."""
    from access import Access,SshTransport,vm_config
    from lease import VmLease,inspect
    from vm_client import vm_call
    from recovery import receipt,read
    value=job.get('updateTransfer')
    if not value or not value.get('target') or not value.get('tmp') or not value.get('final'):
        raise DevelopmentFault('The original Inbox names/target were not durably recorded.')
    original=read(store.root/'UpdateTransferWork'/job['id']/'transport.json')
    if (any(original.get(key)!=value.get(key) for key in ('jobId','projectId','tmp','final','bytes','sha256','target','renameIntent','packageArtifactId')) or value['jobId']!=job['id'] or value['projectId']!=store.id
        or any(value[key]!=job['updatePackage'][key] for key in ('bytes','sha256'))
        or value['packageArtifactId']!=job['packageArtifactId']):
        raise DevelopmentFault('The original immutable transport binding changed.')
    from inbox_sftp import inbox_path
    inbox_path(value['tmp'],'TMP');inbox_path(value['final'],'R4U')
    if value['tmp'].rsplit('.',1)[0]!=value['final'].rsplit('.',1)[0]:
        raise DevelopmentFault('The recorded Inbox transport pair differs.')
    vm=vm_config(store.r4os,value['target']['vmId'])
    if (store.project['vmId']!=vm['id'] or vm['imageSha256']!=value['target']['imageSha256']
            or vm.get('systemGeneration')!=value['target'].get('systemGeneration')):
        raise DevelopmentFault('The original Inbox target system changed. Its files were preserved.')
    scope={'kind':'recovery','vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256']}
    with VmLease(store.projects,vm['id'],scope) as lease:
        info=await vm_call(lease,'info')
        if info['vm']['state']!='running':raise DevelopmentFault('Start the original VM explicitly before reading its Inbox state.')
        boot=await host.boots.ensure(vm,info['invocationId']);scope['bootId']=boot['bootId'];save(lease.root/'leases'/(lease.id+'.json'),lease.value)
        access=Access(store.projects,store.r4os,None)
        async with SshTransport(access,vm,lease) as ssh:
            async with InboxSftp(ssh,lambda:inspect(store.projects,lease.id,lease.token)) as client:
                temporary=await client.get_hash(value['tmp'],value['bytes'])
                final=await client.get_hash(value['final'],value['bytes'])
    if client.exit_code!=0:raise DevelopmentFault('The read-only Inbox observation did not end cleanly.')
    observation={'tmp':temporary,'final':final,'readOnly':True,'observedAt':now()}
    confirmed=bool(value.get('renameIntent') and temporary is None and final and final['bytes']==value['bytes'] and final['sha256']==value['sha256'])
    if confirmed:
        value={**value,'published':True,'phase':'published','guestPath':'C:'+value['final'][2:].replace('/',chr(92)),'reconciliation':observation}
        return store.recovered(job['id'],'completed',receipt('inbox-known-path-readback',publicationConfirmed=True),updateTransfer=value,error=None,exitCode=0)
    return store.recovered(job['id'],'unknown',receipt('inbox-known-path-readback',publicationConfirmed=False),
        updateTransfer={**value,'reconciliation':observation},error='The original Inbox publication is unconfirmed. No write was repeated; use a clearly new job/name for a fresh attempt.')
