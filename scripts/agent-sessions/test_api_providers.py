"""Isolated private-store/endpoint/retirement cases; no network or inference."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import uuid

from api_endpoint import endpoint,resolved_addresses
from api_provider_store import ApiProviders
from store import ProjectFault

def request():return str(uuid.uuid4())


class Providers(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=ApiProviders(self.root)
        self.secret='fixture-only-bearer-key-first';self.second='fixture-only-bearer-key-second'
        self.input={'requestId':request(),'name':'Own API fixture','kind':'openai-compatible','baseUrl':'https://models.example.test/v1/',
            'protocol':'responses','auth':'bearer','key':self.secret}
    def create(self):return self.store.mutate('create',None,self.input)['provider']
    def keys(self):
        with closing(sqlite3.connect(self.store.root/'Private/Secrets.sqlite')) as db:return db.execute('SELECT revision,value FROM credentials ORDER BY revision').fetchall()

    def test_masked_atomic_revisions_and_idempotent_requests(self):
        self.assertEqual(self.store.listing(),[]);self.assertFalse(self.store.root.exists())
        value=self.create();ident=value['id'];self.assertTrue(value['keyConfigured']);self.assertEqual(value['runtime'],'not-qualified')
        self.assertNotIn(self.secret,json.dumps(value));self.assertNotIn(self.secret,json.dumps(self.store.listing()))
        self.assertEqual(self.create(),value)
        with self.assertRaises(ProjectFault):self.store.mutate('create',None,{**self.input,'key':self.second})
        self.assertEqual(self.keys(),[(1,self.secret)])
        for path in (self.store.root,self.store.root/'Private'):self.assertEqual(path.stat().st_mode&0o777,0o700)
        for path in (self.store.root/'Providers.sqlite',self.store.root/'Private/Secrets.sqlite'):self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertNotIn(self.secret.encode(),(self.store.root/'Providers.sqlite').read_bytes())
        with self.assertRaises(ProjectFault):self.store.mutate('update',ident,{'requestId':request(),'revision':99,'key':self.second})
        with self.assertRaises(ProjectFault):self.store.mutate('update',ident,{'requestId':request(),'revision':1,'baseUrl':'https://other.example.test/v1'})
        data={'requestId':request(),'revision':1,'baseUrl':'https://other.example.test/v1','key':self.second}
        updated=self.store.mutate('update',ident,data);self.assertEqual(updated['provider']['credentialRevision'],2)
        self.assertEqual(self.keys(),[(2,self.second)]);self.assertNotIn(self.secret.encode(),(self.store.root/'Private/Secrets.sqlite').read_bytes())
        self.assertEqual(self.store.receipt(ident,data['requestId']),updated)
        removed=self.store.mutate('update',ident,{'requestId':request(),'revision':2,'key':None})['provider']
        self.assertFalse(removed['keyConfigured']);self.assertFalse(removed['enabled']);self.assertEqual(self.keys(),[])

    def test_live_revision_hold_and_original_retirement(self):
        value=self.create();ident=value['id']
        with closing(sqlite3.connect(self.store.root/'Providers.sqlite')) as db,db:
            db.execute("INSERT INTO leases VALUES (?,?,1,1,'unknown','own-original-binding')",(request(),ident))
        self.store.mutate('update',ident,{'requestId':request(),'revision':1,'key':self.second})
        self.assertEqual(self.keys(),[(1,self.secret),(2,self.second)])
        data={'requestId':request(),'revision':2};pending=self.store.mutate('delete',ident,data)
        self.assertEqual(pending['state'],'pending');self.assertFalse(self.store.get(ident)['enabled'])
        with self.assertRaises(ProjectFault):self.store.mutate('delete',ident,data,finish=True)
        self.assertEqual(self.store.receipt(ident,data['requestId'])['state'],'pending');self.assertEqual(len(self.keys()),2)
        with closing(sqlite3.connect(self.store.root/'Providers.sqlite')) as db,db:db.execute("UPDATE leases SET state='released'")
        done=self.store.mutate('delete',ident,data,finish=True);self.assertEqual(done['state'],'complete');self.assertEqual(self.keys(),[])
        self.assertEqual(self.store.listing(),[])
        with self.assertRaises(ProjectFault) as caught:self.store.get(ident)
        self.assertEqual(caught.exception.code,410);self.assertEqual(self.store.receipt(ident,data['requestId']),done)
        self.assertEqual(self.store.mutate('delete',ident,data),done)

    def test_transaction_fault_preserves_both_stores_and_private_paths(self):
        value=self.create();ident=value['id']
        with closing(sqlite3.connect(self.store.root/'Providers.sqlite')) as db,db:
            db.execute("CREATE TRIGGER fail_revision BEFORE INSERT ON revisions BEGIN SELECT RAISE(ABORT,'isolated fault'); END")
        with self.assertRaises(ProjectFault):self.store.mutate('update',ident,{'requestId':request(),'revision':1,'key':self.second})
        self.assertEqual(self.store.get(ident),value);self.assertEqual(self.keys(),[(1,self.secret)])
        secret=self.store.root/'Private/Secrets.sqlite';saved=secret.with_suffix('.original');secret.rename(saved);secret.symlink_to(saved)
        with self.assertRaises(ProjectFault):self.store.get(ident)
        secret.unlink();saved.rename(secret);secret.chmod(0o644)
        with self.assertRaises(ProjectFault):self.store.listing()
        self.assertEqual(secret.stat().st_mode&0o777,0o644)

    def test_concurrent_updates_admit_only_one_original_revision(self):
        value=self.create()
        def change(label):
            try:return self.store.mutate('update',value['id'],{'requestId':request(),'revision':1,'name':label})['state']
            except ProjectFault as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,('First edit','Second edit')))
        self.assertCountEqual(results,['complete',409]);self.assertEqual(self.store.get(value['id'])['revision'],2)
        self.assertEqual(self.keys(),[(1,self.secret)])

    def test_original_run_reservation_rotation_claim_and_disconnect(self):
        value=self.create();ident=value['id'];run,owner,sid,rid=(request() for _ in range(4))
        selected={k:value[k] for k in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision')}
        config={'apiProvider':selected,'apiRunId':run}
        args=(run,'project',owner,sid,rid,config)
        self.store.reserve(*args);self.store.reserve(*args)
        with self.assertRaises(ProjectFault):self.store.reserve(run,'skill',owner,sid,rid,config)
        self.store.mutate('update',ident,{'requestId':request(),'revision':1,'key':self.second})
        self.assertEqual(len(self.keys()),2)
        from attachment_store import birth
        worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'fixture-only'}
        self.assertEqual(self.store.claim(*args,worker),self.secret)
        with self.assertRaises(ProjectFault):self.store.claim(*args,worker)
        data={'requestId':request(),'revision':2}
        self.assertEqual(self.store.mutate('disconnect',ident,data)['state'],'pending')
        with self.assertRaises(ProjectFault):self.store.mutate('disconnect',ident,data,finish=True)
        with self.assertRaises(ProjectFault):self.store.release(*args,{**worker,'birth':'foreign'})
        self.assertEqual(len(self.keys()),2)
        self.store.release(*args,worker);self.assertEqual(self.keys(),[(2,self.second)])
        self.assertEqual(self.store.mutate('disconnect',ident,data,finish=True)['state'],'complete')
        self.assertEqual(self.keys(),[])

    def test_disconnect_closes_unclaimed_admission_without_exposing_key(self):
        value=self.create();run,owner,sid,rid=(request() for _ in range(4))
        config={'apiRunId':run,'apiProvider':{k:value[k] for k in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision')}}
        args=(run,'skill',owner,sid,rid,config);self.store.reserve(*args)
        data={'requestId':request(),'revision':1};self.store.mutate('delete',value['id'],data)
        from attachment_store import birth
        worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'fixture-only'}
        with self.assertRaises(ProjectFault):self.store.claim(*args,worker)
        self.assertEqual(self.store.mutate('delete',value['id'],data,finish=True)['state'],'complete')
        self.assertEqual(self.keys(),[])

    def test_api_queue_cancellation_and_deletion_guard_preserve_legacy_session(self):
        from unittest.mock import patch,AsyncMock
        from test_runs import Runs
        from session_store import encode
        from profile import PROFILE,CODEX_VERSION,CODEX_SHA256
        from message_store import Messages
        from host import Host
        from session_delete import inspect as inspect_session
        fixture=Runs();fixture.setUp()
        try:
            fixture.providers.chmod(0o700);apis=ApiProviders(fixture.providers)
            provider=apis.mutate('create',None,self.input)['provider'];ident=provider['id']
            models=apis.root/'Models';models.mkdir(mode=0o700)
            catalog=models/(ident+'.json');catalog.write_text(encode({'schema':1,'providerId':ident,'configRevision':1,
                'models':[{'slug':'fixture','visibility':'list','use_responses_lite':False,'input_modalities':['text'],
                    'supported_reasoning_levels':[{'effort':'low'}]}]}));catalog.chmod(0o600)
            with fixture.open() as store,patch('session_store.engine',return_value={'profile':PROFILE,'version':CODEX_VERSION,'sha256':CODEX_SHA256,'available':True}):
                session=store.create({'requestId':request(),'name':'Own API session','providerId':ident,'model':'fixture','effort':'low'},fixture.providers)
                sid=session['id'];self.assertFalse(session['webSearchEnabled']);self.assertFalse(session['imageGenerationEnabled'])
                with self.assertRaises(ProjectFault):store.update(fixture.sid,{'revision':1,'providerId':ident},fixture.providers)
                legacy=dict(store.row(fixture.sid));messages=Messages(store);rid=request()
                receipt,fresh=messages.accept(sid,{'requestId':rid,'revision':1,'text':'Own queued input','mode':'queue'},fixture.providers)
                self.assertTrue(fresh);self.assertEqual(receipt['state'],'queued')
                self.assertTrue(apis.held_session(ident,'project',fixture.pid,sid))
                self.assertFalse(apis.held_session(ident,'project',fixture.pid,fixture.sid))
                host=Host({'projects':str(fixture.projects),'r4os':str(fixture.r4os),'providers':str(fixture.providers),'uid':os.getuid()})
                with patch('session_delete.unit_states',AsyncMock(return_value=False)):
                    before=asyncio.run(inspect_session(host,store,sid))[0]
                    self.assertFalse(before['allowed']);self.assertTrue(any('API admission' in v for v in before['blockers']))
                    result=messages.control(sid,{'requestId':request(),'revision':messages.snapshot(sid)['revision'],
                        'action':'cancel','messageId':rid},fixture.providers)
                    self.assertFalse(apis.held_session(ident,'project',fixture.pid,sid))
                    self.assertTrue(asyncio.run(inspect_session(host,store,sid))[0]['allowed'])
                self.assertEqual(dict(store.row(fixture.sid)),legacy)
                self.assertNotIn(self.secret,encode(result))
        finally:fixture.tearDown()

    def test_endpoint_and_key_boundaries_before_transport(self):
        self.assertEqual(endpoint('http://localhost:11434/v1/','local')['baseUrl'],'http://127.0.0.1:11434/v1')
        self.assertEqual(endpoint('https://[::1]:8443/v1','local')['baseUrl'],'https://[::1]:8443/v1')
        value=endpoint('https://models.example.test/v1','openai-compatible')
        self.assertEqual(resolved_addresses(value,['8.8.8.8']),['8.8.8.8'])
        for addresses in ([],['127.0.0.1'],['8.8.8.8','169.254.169.254'],['224.0.0.1']):
            with self.subTest(addresses=addresses),self.assertRaises(ProjectFault):resolved_addresses(value,addresses)
        for url,kind in [('http://models.example.test/v1','openai-compatible'),('https://127.0.0.1/v1','openai-compatible'),
                ('http://169.254.169.254/v1','local'),('http://127.0.0.1:5010/api','local'),('http://127.0.0.1:22/v1','local'),
                ('http://[::ffff:127.0.0.1]:8080/v1','local'),('http://192.168.0.1/v1/../secrets','local'),
                ('https://models.example.test/v1?key=bad','openai-compatible'),('https://user:pass@models.example.test/v1','openai-compatible'),
                ('https://models.example.test/v1#part','openai-compatible'),('https://models.example.test/v1%2f..','openai-compatible'),
                ('https://metadata.google.internal/v1','openai-compatible'),('https://localhost./v1','openai-compatible'),
                ('http://models.example.test/v1','local'),('https://models.example.test\\@127.0.0.1/v1','openai-compatible')]:
            with self.subTest(url=url),self.assertRaises(ProjectFault):endpoint(url,kind)
        value=self.create()
        for token in ('bad\nheader','bad\rheader','bad key','', '🦄'):
            with self.subTest(token=repr(token)),self.assertRaises(ProjectFault):
                self.store.mutate('update',value['id'],{'requestId':request(),'revision':1,'key':token})
        self.assertEqual(self.store.get(value['id']),value)

    def test_host_closes_admission_before_cancel_and_receipt_never_cancels(self):
        from host import Host
        value=self.create();calls=[];available=[False]
        host=SimpleNamespace(config={'providers':str(self.root)})
        async def handle(data):
            if data.get('operation')=='cancel_provider':
                calls.append(data['providerId']);self.assertFalse(self.store.get(value['id'])['enabled'])
                if not available[0]:raise ProjectFault('Isolated unconfirmed worker.',503)
                return {'stopped':True}
            return await Host.handle(host,data)
        host.handle=handle;body={'requestId':request(),'revision':1}
        call={'operation':'api_provider','action':'disconnect','id':value['id'],'input':body}
        with self.assertRaises(ProjectFault):asyncio.run(handle(call))
        self.assertEqual(self.keys(),[(1,self.secret)])
        result=asyncio.run(handle({'operation':'api_provider','action':'receipt','id':value['id'],'requestId':body['requestId']}))
        self.assertEqual(result['state'],'pending');self.assertEqual(len(calls),1)
        available[0]=True;result=asyncio.run(handle(call));self.assertEqual(result['state'],'complete');self.assertEqual(self.keys(),[])
        self.assertEqual(len(calls),2);asyncio.run(handle(call));self.assertEqual(len(calls),2)


if __name__=='__main__':unittest.main()
