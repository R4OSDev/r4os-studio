"""Native framing faults, create-only paths, local binding and no-write reconciliation."""
import asyncio
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from inbox_sftp import InboxSftp, PREFIX, Reader, RemoteStatus, string, u32, u64, inbox_path
from test_sysupd import IDLE, capture, ProbeAdmission
from update_transfer import Transfer

TMP=PREFIX+'U123ABCD.TMP'
FINAL=PREFIX+'U123ABCD.R4U'

class Framing(unittest.IsolatedAsyncioTestCase):
    def client(self, responses):
        client=InboxSftp(None);client.send=AsyncMock()
        client.packet=AsyncMock(side_effect=responses)
        return client
    async def test_create_only_flags_and_explicit_native_refusals(self):
        client=self.client([bytes([102])+u32(1)+string(b'h')])
        self.assertEqual(await client.open(TMP,True),b'h')
        sent=client.send.await_args.args[0];reader=Reader(sent[5:])
        self.assertEqual(reader.text(),TMP.encode());self.assertEqual(reader.number(),58)
        client=self.client([bytes([101])+u32(1)+u32(4)+string('exists')+string('')])
        with self.assertRaises(RemoteStatus):await client.open(TMP,True)
        self.assertEqual(client.send.await_count,1)
    async def test_only_no_such_file_is_missing_and_nonregular_collision_is_retained(self):
        client=self.client([bytes([101])+u32(1)+u32(2)+string('missing')+string('')])
        self.assertIsNone(await client.stat(TMP))
        client=self.client([bytes([101])+u32(1)+u32(3)+string('denied')+string('')])
        with self.assertRaises(RemoteStatus):await client.stat(TMP)
        client=self.client([bytes([105])+u32(1)+u32(5)+u64(0)+u32(0o40700)])
        self.assertFalse((await client.stat(TMP))['regular'])
    async def test_lost_write_close_rename_responses_are_unknown_without_retry(self):
        for operation,args in [('write',(b'h',0,b'data')),('close',(b'h',True)),('rename',(TMP,FINAL)),('open',(TMP,True))]:
            client=self.client([asyncio.IncompleteReadError(b'',4)])
            with self.assertRaises(UnconfirmedGuestEffect):await getattr(client,operation)(*args)
            self.assertEqual(client.send.await_count,1)
    async def test_wrong_reply_id_and_malformed_mutation_ack_are_unknown(self):
        for response in [bytes([101])+u32(99)+u32(0)+string('')+string(''),bytes([102])+u32(1)+string(b'wrong')]:
            client=self.client([response])
            with self.assertRaises(UnconfirmedGuestEffect):await client.rename(TMP,FINAL)
    async def test_only_reserved_same_short_pair_and_no_final_write(self):
        client=self.client([])
        for path in ['/C/R4OS/CONFIG/MODULES.JSON',PREFIX+'../U123ABCD.TMP',PREFIX+'LONGNAME9.R4U',PREFIX+'U123abcd.R4U']:
            with self.assertRaises(DevelopmentFault):inbox_path(path)
        with self.assertRaises(DevelopmentFault):await client.open(FINAL,True)
        with self.assertRaises(DevelopmentFault):await client.rename(TMP,PREFIX+'U123ABCE.R4U')
        client.send.assert_not_awaited()
    async def test_local_hash_mismatch_is_checked_before_first_remote_open(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'package.R4U';path.write_bytes(b'a'*100)
            client=self.client([])
            with self.assertRaisesRegex(DevelopmentFault,'hash changed'):
                await client.put(TMP,path,{'bytes':100,'sha256':'0'*64})
            client.send.assert_not_awaited()
    async def test_local_change_during_stream_never_closes_or_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'package.R4U';path.write_bytes(b'a'*20000)
            client=InboxSftp(None);client.open=AsyncMock(return_value=b'h');client.close=AsyncMock()
            async def changed(*args):path.write_bytes(b'b'*20000)
            client.write=AsyncMock(side_effect=changed)
            with self.assertRaisesRegex(DevelopmentFault,'changed during transfer'):
                await client.put(TMP,path,{'bytes':20000,'sha256':hashlib.sha256(b'a'*20000).hexdigest()})
            client.close.assert_not_awaited()

class Admission(ProbeAdmission):
    async def test_transfer_request_replay_is_separate_from_probe_and_serializes_project(self):
        from update_probe import admit
        job,fresh=admit(self.store,self.request,None,self.vm,kind='update_transfer')
        self.assertTrue(fresh);self.assertEqual(job['kind'],'update_transfer')
        self.assertEqual(admit(self.store,self.request,None,None,kind='update_transfer'),(job,False))
        with self.assertRaises(DevelopmentFault):admit(self.store,self.request,None,self.vm)
        with self.assertRaises(DevelopmentFault):self.store.admit('build',self.fixture.fixture.input())

class Publication(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, fault=None):
        with tempfile.TemporaryDirectory() as temp:
            work=Path(temp);data=b'R4U2'+b'a'*100;local=work/'package.R4U';local.write_bytes(data)
            updates=[];intents=[]
            class Store:
                id='project';projects=work;r4os=work
                def update(self,ident,state=None,**fields):updates.append((state,fields));return {'state':state,**fields}
                def evidence(self,ident):return work
            transfer=object.__new__(Transfer);transfer.store=Store();transfer.job={'id':'job','binding':{'id':'vm'}};transfer.work=work;transfer.frozen=local
            transfer.package={'id':'package','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
            transfer.value={'schema':1,'jobId':'job','projectId':'project','packageArtifactId':'package',**transfer.package,'phase':'preparing','collisions':[]}
            def persist():intents.append(dict(transfer.value))
            transfer.persist=persist
            class SSH:
                def __init__(self,*a):pass
                async def __aenter__(self):return self
                async def __aexit__(self,*a):pass
                async def exec(self,command,**kwargs):
                    if command!='SYSUPD STATUS':raise AssertionError('No SYSUPD mutation allowed during transfer')
                    return capture(IDLE)
            class Wire:
                def __init__(self,*a):self.files={};self.events=[];self.counts={};self.exit_code=0;self.stderr=b'';self.renames=0;self.collision=True
                async def __aenter__(self):return self
                async def __aexit__(self,*a):pass
                async def stat(self,path):
                    if fault=='collision' and self.collision:
                        if path.endswith('.R4U'):self.collision=False
                        return {'bytes':100,'regular':True}
                    if fault=='final-race' and path.endswith('.R4U') and self.files:return {'bytes':9,'regular':True}
                    return {'bytes':len(self.files[path]),'regular':True} if path in self.files else None
                async def put(self,path,local,expected,progress,closing):
                    self.files[path]=local.read_bytes();progress(len(data));closing()
                    self.assert_intent=any(x.get('phase')=='upload_intent' for x in intents)
                    if fault=='close-loss':raise UnconfirmedGuestEffect('close lost')
                    return {'bytes':len(data),'sha256':expected['sha256'],'closeAcknowledged':True}
                async def get_hash(self,path,maximum):
                    if path not in self.files:return None
                    return {'bytes':len(data),'sha256':('0'*64 if fault=='corrupt' else hashlib.sha256(self.files[path]).hexdigest()),'fullReadVerified':True}
                async def rename(self,source,destination):
                    self.renames+=1
                    if not any(x.get('renameIntent') for x in intents):raise AssertionError('Missing durable rename intent')
                    self.files[destination]=self.files.pop(source)
                    if fault=='rename-loss':raise UnconfirmedGuestEffect('rename lost')
            wire=Wire()
            from sysupd_text import parse
            observation={'hostKeyFingerprint':'SHA256:test','status':parse('STATUS',capture(IDLE))}
            with patch('access.Access'),patch('access.SshTransport',SSH),patch('update_transfer.InboxSftp',return_value=wire),patch('vm_worker.guard'),patch('update_transfer.artifact',return_value=transfer.package):
                error=None
                try:result=await transfer.publish(None,{'vmId':'vm'},observation)
                except DevelopmentFault as caught:error=caught;result=None
            return result,error,wire,intents,transfer.value
    async def test_complete_readback_then_rename_and_clean_exit(self):
        result,error,wire,intents,value=await self.scenario()
        self.assertIsNone(error);self.assertEqual(result['state'],'completed');self.assertEqual(wire.renames,1)
        self.assertTrue(value['published']);self.assertTrue(wire.assert_intent);self.assertEqual(value['finalRead'],value['readback'])
        self.assertEqual(value['guestPath'],'C:'+value['final'][2:].replace('/',chr(92)))
    async def test_collision_uses_new_pair_preserving_existing_names(self):
        _,error,wire,intents,value=await self.scenario('collision')
        self.assertIsNone(error);self.assertEqual(len(value['collisions']),1)
        self.assertNotEqual(value['tmp'],value['collisions'][0]['tmp'])
    async def test_corrupt_readback_or_new_final_collision_never_renames(self):
        for fault in ['corrupt','final-race']:
            _,error,wire,intents,value=await self.scenario(fault)
            self.assertIsInstance(error,DevelopmentFault);self.assertEqual(wire.renames,0);self.assertFalse(value.get('published',False))
    async def test_lost_close_or_rename_ack_keeps_intents_and_has_no_write_retry(self):
        for fault,count in [('close-loss',0),('rename-loss',1)]:
            _,error,wire,intents,value=await self.scenario(fault)
            self.assertIsInstance(error,UnconfirmedGuestEffect);self.assertEqual(wire.renames,count)
            self.assertTrue(any(x['phase']=='close_intent' for x in intents))
            if count:self.assertTrue(value['renameIntent']);self.assertEqual(len(wire.files),1)


class Reconciliation(unittest.IsolatedAsyncioTestCase):
    async def test_only_original_paths_are_read_after_unknown_rename(self):
        import update_transfer
        value={'schema':1,'jobId':'job','projectId':'project','packageArtifactId':'package','bytes':100,'sha256':'a'*64,
               'tmp':TMP,'final':FINAL,'renameIntent':True,'target':{'vmId':'vm','imageSha256':'b'*64,'systemGeneration':None}}
        calls=[]
        class Lease:
            root=Path('/unused');id='lease';token='token';value={}
            def __init__(self,*a):pass
            def __enter__(self):return self
            def __exit__(self,*a):pass
        class SSH:
            def __init__(self,*a):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*a):pass
        class ReadOnlyWire(SSH):
            exit_code=0
            async def get_hash(self,path,maximum):
                calls.append(path)
                return None if path==TMP else {'bytes':100,'sha256':'a'*64,'fullReadVerified':True}
        store=SimpleNamespace(root=Path('/unused'),projects=Path('/unused'),r4os=Path('/unused'),id='project',project={'vmId':'vm'},
            recovered=lambda *args,**fields:fields)
        job={'id':'job','kind':'update_transfer','state':'unknown','packageArtifactId':'package',
             'updatePackage':{'bytes':100,'sha256':'a'*64},'updateTransfer':value}
        vm={'id':'vm','revision':'rev','imageSha256':'b'*64,'imageId':'base'}
        host=SimpleNamespace(boots=SimpleNamespace(ensure=AsyncMock(return_value={'bootId':'boot'})))
        with patch('recovery.read',return_value=value),patch('access.vm_config',return_value=vm),patch('lease.VmLease',Lease),patch('vm_client.vm_call',new_callable=AsyncMock,return_value={'vm':{'state':'running'},'invocationId':'i'}),patch('update_transfer.save'),patch('access.Access'),patch('access.SshTransport',SSH),patch('update_transfer.InboxSftp',ReadOnlyWire):
            result=await update_transfer.reconcile(store,job,host)
        self.assertEqual(calls,[TMP,FINAL]);self.assertTrue(result['updateTransfer']['published'])
        self.assertTrue(result['updateTransfer']['reconciliation']['readOnly'])

if __name__=='__main__':unittest.main()

