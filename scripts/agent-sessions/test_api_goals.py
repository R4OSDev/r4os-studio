"""API Goal intent/lease boundaries and unchanged legacy runs; no inference."""
import hashlib
import json
import os
import unittest
import asyncio
from types import SimpleNamespace

from api_provider_store import ApiProviders
from api_catalog import Catalogs
from goal_store import Goals,exists
from profile import CODEX_SHA256
from run_store import admit,get_run
from session_store import encode
from store import ProjectFault
from worker import Worker
from attachment_store import birth
from test_api_usage import ApiUsageTests,request
import test_runs as fixtures


class ApiGoals(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    ready=ApiUsageTests.ready

    def prepared(self,store):
        self.ready(store,'responses')
        Catalogs(self.providers).save_model(self.connection['id'],{'requestId':request(),'providerRevision':1,
            'catalogRevision':0,'model':{'id':'owned/exact-model','contextWindow':8192,
                'capabilities':{'text':'supported','functionTools':'supported','streaming':'supported','reasoning':'unsupported'}}})
        goals=Goals(store);goals.observe(self.sid,self.thread,{'threadId':self.thread,'objective':'Complete this own checked Goal.',
            'status':'paused','tokensUsed':44,'timeUsedSeconds':5,'createdAt':1,'updatedAt':1,'tokenBudget':1000})
        data={'requestId':request(),'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1}
        goals.accept(self.sid,data)
        return data

    def test_goal_protocol_and_original_play_freeze_before_api_lease_claim(self):
        with self.open() as store:
            play=self.prepared(store)
            run,_=admit(store,self.sid,{'requestId':play['requestId'],'goalRequestId':play['requestId'],
                'mode':'goal','revision':1,'liveGoalPreparation':1},self.providers)
            original=get_run(store,run['id'])['config'];config=json.loads(original)
            self.assertEqual(config['apiGoalProtocol'],1);self.assertTrue(config['nativeGoalPreparation'])
            self.assertEqual(config['goalExecution']['requestId'],play['requestId'])
            self.assertEqual(config['goalExecution']['threadId'],self.thread)
            meta={'release':'own-goal-case','pid':os.getpid(),'birth':birth(os.getpid())}
            key=self.api.claim(run['id'],'project',self.pid,self.sid,play['requestId'],config,meta)
            self.assertEqual(key,'only-owned-api-usage-key');self.assertNotIn(key,original)
            self.api.validate_active(run['id'],'project',self.pid,self.sid,play['requestId'],config,meta)
            changed={**config,'apiGoalProtocol':2}
            with self.assertRaises(ProjectFault):
                self.api.validate_active(run['id'],'project',self.pid,self.sid,play['requestId'],changed,meta)
            self.assertEqual(get_run(store,run['id'])['config'],original)
            self.assertEqual(config['goalExecution']['captureSha256'],hashlib.sha256(encode(Goals(store).snapshot(self.sid)['goal']).encode()).hexdigest())
            self.api.release(run['id'],'project',self.pid,self.sid,play['requestId'],config,meta)

    def test_unqualified_api_runtime_cannot_accept_a_goal_intent(self):
        with self.open() as store:
            self.ready(store);engine=json.loads(store.row(self.sid)['engine']);engine['sha256']='0'*64
            with store.db:store.db.execute('UPDATE sessions SET engine=? WHERE id=?',(encode(engine),self.sid))
            with self.assertRaises(ProjectFault):
                Goals(store).accept(self.sid,{'requestId':request(),'revision':0,'action':'save','objective':'Own text'})
            self.assertFalse(exists(store))
            with self.api.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM leases').fetchone()[0],0)

    def test_existing_api_run_is_not_upgraded_or_rewritten_into_goal_preparation(self):
        with self.open() as store:
            config=self.ready(store);config['nativeGoalPreparation']=False
            with store.db:store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(config),self.run))
            original=get_run(store,self.run)['config']
        worker=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),
            'projectId':self.pid,'runId':self.run,'sessionId':self.sid,'release':'own-legacy-api-case'})
        try:
            self.assertIsNone(worker.goal_worker);self.assertIsNone(worker.client)
            self.assertNotIn('apiGoalProtocol',worker.config)
            self.assertEqual(get_run(worker.store,self.run)['config'],original)
            self.assertEqual(worker.config['engine']['sha256'],CODEX_SHA256)
        finally:worker.store.close()


class ApiGoalObservationLimit(unittest.IsolatedAsyncioTestCase):
    async def test_long_goal_keeps_draining_after_bounded_wire_receipts_without_inventing_more(self):
        from api_runtime import ApiRuntime
        reader=asyncio.StreamReader()
        for ordinal in range(1,259):
            reader.feed_data((encode({'event':'usage','ordinal':ordinal,'responseId':'own-response-'+str(ordinal),
                'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}})+'\n').encode())
        reader.feed_eof()
        runtime=ApiRuntime({'id':request(),'kind':'local'},'own-model',None,'/unused-owned-case')
        runtime.child=SimpleNamespace(stdout=reader)
        await runtime.read_origins()
        self.assertTrue(reader.at_eof());self.assertTrue(runtime.origin_error)
        self.assertEqual(len(runtime.usages),256)
        self.assertEqual([value['ordinal'] for value in runtime.usages],list(range(1,257)))
