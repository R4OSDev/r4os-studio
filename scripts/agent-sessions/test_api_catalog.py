"""Catalog atomicity, frozen metadata credentials and original helper recovery."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import uuid

from api_provider_store import ApiProviders
from api_catalog import Catalogs
from api_model_info import native,present
from api_catalog_host import start,recover
from attachment_store import birth
from store import ProjectFault

def request():return str(uuid.uuid4())
def facts(qualified=False):
    return {'id':'own/exact-model','name':'Own model','contextWindow':8192,'maxOutputTokens':2048,
        'capabilities':{'text':'supported','functionTools':'supported','streaming':'supported','reasoning':'unsupported'} if qualified else {}}


class Catalog(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=ApiProviders(self.root);self.store=Catalogs(self.root)
        self.secret='fixture-only-metadata-key'
        self.provider=self.api.mutate('create',None,{'requestId':request(),'name':'Own API','kind':'local',
            'baseUrl':'http://127.0.0.1:11434/v1','protocol':'chat-completions','auth':'bearer','key':self.secret})['provider']
        self.ident=self.provider['id']
    def save(self,value=None):
        return {'requestId':request(),'providerRevision':self.api.get(self.ident)['revision'],
            'catalogRevision':self.store.listing(self.ident)['revision'],'model':value or facts(True)}
    def check(self):return {'requestId':request(),'providerRevision':self.api.get(self.ident)['revision']}
    def keys(self):
        with closing(sqlite3.connect(self.api.root/'Private/Secrets.sqlite')) as db:return db.execute('SELECT value FROM credentials ORDER BY revision').fetchall()

    def test_unknowns_qualification_neutral_descriptor_and_revision_scope(self):
        self.assertFalse(present(facts(),'chat-completions')['available']);self.assertIsNone(native(facts(),'chat-completions'))
        data=self.save();result=self.store.save_model(self.ident,data)
        self.assertEqual(self.store.save_model(self.ident,data),result)
        catalog=self.store.listing(self.ident);self.assertTrue(catalog['models'][0]['available']);self.assertFalse(catalog['metadataCurrent'])
        self.assertEqual(catalog['models'][0]['efforts'],['none']);self.assertEqual(catalog['models'][0]['capabilities']['imageInput'],'unsupported')
        model=self.store.native_models(self.ident)[0];self.assertEqual(model['context_window'],8192);self.assertEqual(model['default_reasoning_level'],'none')
        self.assertFalse(model['supports_reasoning_summary_parameter']);self.assertFalse(model['use_responses_lite'])
        self.api.mutate('update',self.ident,{'requestId':request(),'revision':1,'baseUrl':'http://127.0.0.1:11434/v2'})
        self.assertTrue(self.store.listing(self.ident)['stale']);self.assertEqual(self.store.native_models(self.ident),[])
        changed=facts(True);changed['id']='other/explicit';self.store.save_model(self.ident,self.save(changed))
        self.assertEqual([m['id'] for m in self.store.listing(self.ident)['models']],['other/explicit'])

    def test_atomic_catalog_and_original_receipt_and_create_lookup(self):
        data=self.save();self.store.save_model(self.ident,data);before=self.store.listing(self.ident)
        with self.api.connect(write=True) as db:
            db.execute("CREATE TRIGGER fail_catalog_receipt BEFORE INSERT ON catalog_requests BEGIN SELECT RAISE(ABORT,'isolated fault'); END")
        lost=self.save();lost['model']['name']='Changed'
        with self.assertRaises(ProjectFault):self.store.save_model(self.ident,lost)
        self.assertEqual(self.store.listing(self.ident),before)
        with self.assertRaises(ProjectFault):self.store.receipt(self.ident,lost['requestId'])
        with self.api.connect() as db:rid=db.execute("SELECT id FROM requests WHERE operation='create'").fetchone()[0]
        self.assertEqual(self.api.creation_receipt(rid)['provider']['id'],self.ident)
        self.assertNotIn(self.secret,json.dumps(self.api.creation_receipt(rid)))

    def test_original_metadata_intake_capacity_and_boot_never_replays(self):
        data=self.check();result,fresh=self.store.start_refresh(self.ident,data)
        self.assertTrue(fresh);self.assertEqual(self.store.start_refresh(self.ident,data,False),(result,False))
        with self.assertRaises(ProjectFault):self.store.start_refresh(self.ident,{**data,'providerRevision':7})
        host=SimpleNamespace(config={'providers':str(self.root)},catalog_tasks={})
        asyncio.run(recover(host));self.assertEqual(self.store.receipt(self.ident,data['requestId'])['state'],'failed')
        self.assertEqual(self.keys(),[(self.secret,)])
        with self.assertRaises(ProjectFault):self.store.start_refresh(self.ident,self.check(),False)
        self.assertEqual(self.store.pending(),[])

    def test_unconfirmed_metadata_hold_blocks_retirement_and_preserves_old_key(self):
        data=self.check();self.store.start_refresh(self.ident,data)
        with self.api.connect(write=True) as db:db.execute("UPDATE catalog_requests SET held=1,phase='unknown',child='{}'")
        second='fixture-only-second-key';self.api.mutate('update',self.ident,{'requestId':request(),'revision':1,'key':second})
        self.assertEqual(self.keys(),[(self.secret,),(second,)])
        body={'requestId':request(),'revision':2};self.api.mutate('delete',self.ident,body)
        asyncio.run(recover(SimpleNamespace(config={'providers':str(self.root)},catalog_tasks={})))
        self.assertEqual(self.store.receipt(self.ident,data['requestId'])['state'],'unknown')
        with self.assertRaises(ProjectFault):self.api.mutate('delete',self.ident,body,True)
        self.assertEqual(len(self.keys()),2)

    def test_metadata_refresh_keeps_manual_facts_and_publishes_receipt_atomically(self):
        self.store.save_model(self.ident,self.save());data=self.check();self.store.start_refresh(self.ident,data)
        result=self.store.finish(self.ident,data['requestId'],[facts()])
        self.assertEqual(self.store.receipt(self.ident,data['requestId']),result)
        catalog=self.store.listing(self.ident);self.assertTrue(catalog['metadataCurrent']);self.assertTrue(catalog['models'][0]['available'])
        self.assertEqual(catalog['models'][0]['source']['kind'],'manual');self.assertNotIn(self.secret,json.dumps(catalog))
        data=self.check();self.store.start_refresh(self.ident,data)
        self.store.finish(self.ident,data['requestId'],[{**facts(),'id':'metadata/'+str(i)} for i in range(256)])
        extra=facts(True);extra['id']='manual/beyond-metadata-bound';self.store.save_model(self.ident,self.save(extra))
        self.assertEqual(len(self.store.listing(self.ident)['models']),258)
        from unittest.mock import patch
        from session_store import options
        legacy={'id':request(),'name':'Independent subscription','type':'openai'}
        with patch('session_store.providers',return_value=[legacy,self.provider]),patch('session_store.provider_models',return_value=[{'id':'retained'}]),patch('session_store.engine',return_value={'available':True}),patch.object(Catalogs,'listing',side_effect=ProjectFault('Isolated corrupt catalog.',503)):
            value=options(self.root,self.root)
        self.assertEqual(value['providers'][0]['models'],[{'id':'retained'}]);self.assertEqual(value['providers'][1]['models'],[])


class Transport(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.api=ApiProviders(self.root);self.store=Catalogs(self.root)
        self.calls=[];self.response={'data':[{'id':'own/exact-model','name':'Untrusted name','context_length':12345}]};self.status=200
        self.pause=asyncio.Event();self.pause.set();self.connected=asyncio.Event();self.redirect=None
        async def handle(reader,writer):
            try:
                raw=await reader.readuntil(b'\r\n\r\n');self.calls.append(raw.decode('ascii'));self.connected.set()
                await self.pause.wait();body=json.dumps(self.response).encode()
                header=f'HTTP/1.1 {self.status} Fixture\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n'
                if self.redirect:header+='Location: '+self.redirect+'\r\n'
                writer.write(header.encode()+b'\r\n'+body);await writer.drain()
            except (ConnectionError,asyncio.IncompleteReadError):pass
            finally:writer.close();await writer.wait_closed()
        self.server=await asyncio.start_server(handle,'127.0.0.1',0)
        self.port=self.server.sockets[0].getsockname()[1];self.secret='fixture-only-metadata-key'
        self.provider=self.api.mutate('create',None,{'requestId':request(),'name':'Own metadata','kind':'local','baseUrl':f'http://127.0.0.1:{self.port}/v1',
            'protocol':'chat-completions','auth':'bearer','key':self.secret})['provider'];self.ident=self.provider['id']
        self.host=SimpleNamespace(config={'providers':str(self.root)},catalog_lock=asyncio.Lock(),catalog_tasks={})
    async def asyncTearDown(self):
        self.pause.set();await recover(self.host);self.server.close();await self.server.wait_closed()
    async def check(self):
        data={'requestId':request(),'providerRevision':self.api.get(self.ident)['revision']}
        result=await start(self.host,self.ident,data)
        await asyncio.gather(*list(self.host.catalog_tasks.values()))
        return data,self.store.receipt(self.ident,result['requestId'])

    async def test_real_helper_one_get_no_capability_guessing_or_redirect_key_forwarding(self):
        data,result=await self.check();self.assertEqual(result['state'],'complete')
        self.assertEqual(len(self.calls),1);self.assertTrue(self.calls[0].startswith('GET /v1/models HTTP/1.1'))
        self.assertIn('Authorization: Bearer '+self.secret,self.calls[0])
        catalog=self.store.listing(self.ident);self.assertEqual(catalog['models'][0]['name'],'own/exact-model')
        self.assertIsNone(catalog['models'][0]['contextWindow']);self.assertFalse(catalog['models'][0]['available'])
        self.assertNotIn(self.secret,json.dumps(catalog));await start(self.host,self.ident,data);self.assertEqual(len(self.calls),1)
        self.status=302;self.redirect=f'http://127.0.0.1:{self.port}/leak'
        _,result=await self.check();self.assertEqual(result['state'],'failed');self.assertIn('redirected',result['error'])
        self.assertEqual(len(self.calls),2);self.assertTrue(all('GET /v1/models ' in v for v in self.calls))
        self.status=401;self.response={'error':{'message':self.secret}};_,result=await self.check()
        self.assertNotIn(self.secret,json.dumps(result));self.assertIn('authentication',result['error'])

    async def test_real_key_rotation_preserves_original_hold_until_helper_closes(self):
        self.pause.clear();data={'requestId':request(),'providerRevision':1};await start(self.host,self.ident,data)
        await asyncio.wait_for(self.connected.wait(),5)
        self.api.mutate('update',self.ident,{'requestId':request(),'revision':1,'key':'fixture-only-next-key'})
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM secrets.credentials').fetchone()[0],2)
        self.pause.set();await asyncio.gather(*list(self.host.catalog_tasks.values()))
        self.assertEqual(self.store.receipt(self.ident,data['requestId'])['state'],'failed')
        self.assertEqual(self.store.listing(self.ident)['models'],[])
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM secrets.credentials').fetchone()[0],1)
        self.assertIn(self.secret,self.calls[0]);self.assertNotIn('fixture-only-next-key',self.calls[0])

    async def test_disconnect_cancels_original_transport_without_another_get(self):
        self.pause.clear();data={'requestId':request(),'providerRevision':1};await start(self.host,self.ident,data)
        await asyncio.wait_for(self.connected.wait(),5)
        body={'requestId':request(),'revision':1};self.api.mutate('disconnect',self.ident,body)
        await recover(self.host,self.ident)
        self.assertEqual(self.store.receipt(self.ident,data['requestId'])['state'],'failed')
        self.assertEqual(self.api.mutate('disconnect',self.ident,body,True)['state'],'complete');self.assertEqual(len(self.calls),1)

    async def test_recovery_signals_only_actual_original_child_and_releases_after_exit(self):
        script=str(Path(__file__).with_name('api-models.mjs').resolve())
        data={'requestId':request(),'providerRevision':1};self.store.start_refresh(self.ident,data)
        child=await asyncio.create_subprocess_exec('/usr/bin/node',script,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        proof={'pid':child.pid,'birth':birth(child.pid),'script':script};self.store.claim(self.ident,data['requestId'],proof)
        try:
            await recover(self.host);await asyncio.wait_for(child.wait(),3)
            self.assertEqual(self.store.receipt(self.ident,data['requestId'])['state'],'failed');self.assertEqual(self.calls,[])
        finally:
            if child.returncode is None:child.kill();await child.wait()


if __name__=='__main__':unittest.main()
