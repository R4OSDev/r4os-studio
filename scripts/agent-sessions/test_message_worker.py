"""Original worker socket, concrete native target and uncertain steering receipts."""
import asyncio
import json
import os
import unittest
import uuid
from unittest.mock import patch

import test_runs as fixtures
from attachment_store import birth
from codex_rpc import RPCRejected
from human_context import contexts
from message_store import Messages
from message_worker import MessageWorker, live_message
from run_store import admit, transition
from store import ProjectFault
from worker import Worker


class Steering(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    async def worker(self):
        thread = str(uuid.uuid4())
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers)
            with store.db:store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?',(thread,self.sid))
            transition(store,run['id'],'running',turn_id='current-turn',worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'fixture','messageProtocol':1,'messageTurnActive':True})
        w=Worker({'projects':str(self.projects),'r4os':str(self.r4os),'projectId':self.pid,'sessionId':self.sid,'runId':run['id'],'release':'fixture'})
        w.thread_id=thread;w.turn_id='current-turn'
        class Native:
            def __init__(self):self.calls=[];self.fail=None
            async def request(self,method,params,**kwargs):
                self.calls.append((method,params))
                if self.fail:raise self.fail
                return {'turnId':params['expectedTurnId']}
        w.client=Native();w.message_worker=MessageWorker(w)
        self.addCleanup(w.store.close);self.addAsyncCleanup(w.message_worker.close)
        await w.message_worker.start()
        return w

    def input(self,w):
        return {'requestId':str(uuid.uuid4()),'revision':1,'mode':'steer','text':'Explicit human follow-up',
                'target':{'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}}

    async def test_own_socket_native_target_replay_and_human_provenance(self):
        w=await self.worker();inbox=Messages(w.store);data=self.input(w)
        inbox.accept(self.sid,data,self.providers)
        receipt=await live_message(w.store,self.sid,data['requestId'])
        self.assertEqual(receipt['state'],'accepted')
        self.assertEqual((await live_message(w.store,self.sid,data['requestId'])),receipt)
        self.assertEqual(len(w.client.calls),1)
        self.assertEqual(w.client.calls[0][0],'turn/steer')
        self.assertEqual(w.client.calls[0][1]['expectedTurnId'],'current-turn')
        self.assertEqual(list(contexts(w.store.db,self.sid,w.run_id,{'type':'project','id':self.pid}))[0]['text'],data['text'])
        with self.assertRaises(ProjectFault):inbox.accept(self.sid,{**data,'text':'Changed under same ID'},self.providers)
        other=self.input(w);inbox.accept(self.sid,other,self.providers)
        owner=json.loads(w.store.db.execute('SELECT worker FROM runs WHERE id=?',(w.run_id,)).fetchone()[0])
        with w.store.db:w.store.db.execute('UPDATE runs SET worker=? WHERE id=?',(json.dumps({**owner,'birth':'foreign-generation'}),w.run_id))
        with self.assertRaises(ProjectFault) as error:await live_message(w.store,self.sid,other['requestId'])
        self.assertEqual(error.exception.code,403);self.assertEqual(len(w.client.calls),1)

    async def test_unknown_is_not_retried_and_original_native_event_can_confirm(self):
        w=await self.worker();w.client.fail=asyncio.TimeoutError()
        inbox=Messages(w.store);data=self.input(w);inbox.accept(self.sid,data,self.providers)
        self.assertEqual((await live_message(w.store,self.sid,data['requestId']))['state'],'unknown')
        self.assertEqual((await live_message(w.store,self.sid,data['requestId']))['state'],'unknown')
        self.assertEqual(len(w.client.calls),1)
        await w.notify('item/completed',{'threadId':w.thread_id,'turnId':w.turn_id,'item':{'id':'native-own-id','clientId':data['requestId'],'type':'userMessage','content':[{'type':'text','text':data['text']}]}})
        self.assertEqual(inbox.receipt(self.sid,data['requestId'])['state'],'accepted')
        self.assertEqual(len([i for i in w.store.history(self.sid)['items'] if i['id']=='user-'+data['requestId']]),1)
        self.assertEqual(w.store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)

    async def test_stop_and_native_rejection_never_fallback_to_a_new_turn(self):
        w=await self.worker();inbox=Messages(w.store);data=self.input(w)
        inbox.accept(self.sid,data,self.providers);w.stopping=True
        self.assertEqual((await live_message(w.store,self.sid,data['requestId']))['state'],'rejected')
        self.assertFalse(w.client.calls)
        w.stopping=False;w.client.fail=RPCRejected(-32600)
        later=self.input(w);inbox.accept(self.sid,later,self.providers)
        self.assertEqual((await live_message(w.store,self.sid,later['requestId']))['state'],'rejected')
        self.assertEqual(w.client.calls[0][0],'turn/steer')
        self.assertEqual(w.store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)

    async def test_coordinator_uses_original_bound_worker_without_waiting_under_its_lock(self):
        from host import Host
        w=await self.worker()
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        meta={'projectId':self.pid,'sessionId':self.sid,'release':'fixture'}
        host.active[w.run_id]=meta
        data=self.input(w)
        with patch('host.validate_release') as pinned:
            result=await host.handle({'operation':'submit_message','projectId':self.pid,'sessionId':self.sid,'input':data})
            pinned.assert_called_once_with(meta)
        self.assertEqual(result['state'],'pending')
        self.assertFalse(host.lock.locked())
        await asyncio.gather(*tuple(host.message_tasks.values()))
        self.assertEqual(Messages(w.store).receipt(self.sid,data['requestId'])['state'],'accepted')
        foreign={**self.input(w),'target':{**data['target'],'runId':str(uuid.uuid4())}}
        with self.assertRaises(ProjectFault):
            await host.handle({'operation':'submit_message','projectId':self.pid,'sessionId':self.sid,'input':foreign})


if __name__ == '__main__':unittest.main()
