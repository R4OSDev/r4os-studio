"""Original bound waiting, durable human resume and passive recovery."""
import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock
import uuid

from claude_history import ClaudeHistory
from claude_messages import validate_queue
from claude_run_leases import ClaudeRunLeases
from claude_waiting import public_target
from host import Host
from message_store import Messages
from run_store import admit,get_run,transition
from session_store import encode
from store import ProjectFault
import test_claude_messages as fixtures


def uid():return str(uuid.uuid4())


class ClaudeWaiting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f=fixtures.ClaudeMessages();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def source(self):
        f=self.f;store=self.enterContext(f.open())
        run,_=admit(store,f.sid,{'requestId':uid(),'revision':1,'text':'Own original response'},f.providers)
        config,worker,lease=f.opening(store,run)
        target=public_target(store,get_run(store,run['id']))
        self.assertEqual(target,{'runId':run['id'],'nativeSessionId':f.native})
        return store,run,config,worker,lease,target

    def waiting(self,store,target):
        data=self.f.message_input()|{'afterRun':target}
        receipt,fresh=Messages(store).accept(self.f.sid,data,self.f.providers);self.assertTrue(fresh)
        return data,receipt,json.loads(Messages(store).row(self.f.sid,data['requestId'])['frozen'])

    def end(self,store,run,worker,lease,state='completed'):
        # Controlled metadata case only. The actual CLI/history boundary is
        # checked separately; this helper is not a native completion claim.
        history=ClaudeHistory(store,self.f.sid);value=history.get()
        with store.db:history.save({**value,'phase':'ready','activeRunId':None})
        ClaudeRunLeases(self.f.providers).finish_lease(lease,worker,True)
        transition(store,run['id'],state)

    def resume(self,store):
        messages=Messages(store);command={'requestId':uid(),'revision':messages.snapshot(self.f.sid)['revision'],'action':'resume'}
        result=messages.control(self.f.sid,command,self.f.providers)
        return command,result

    async def test_wait_intent_has_exact_target_and_receipt_without_invented_native_turn(self):
        store,run,config,worker,lease,target=self.source();messages=Messages(store)
        data,receipt,frozen=self.waiting(store,target)
        self.assertEqual(receipt['state'],'queued');self.assertEqual(receipt['mode'],'queue')
        self.assertEqual(receipt['afterRun'],target);self.assertIsNone(receipt['target']);self.assertIsNone(receipt['runId'])
        self.assertEqual(messages.accept(self.f.sid,data,self.f.providers),(receipt,False))
        self.assertEqual(frozen['afterRun'],target);self.assertEqual(frozen['claudeQueue']['source']['configSha256'],__import__('claude_messages').digest(config))
        self.assertNotIn('afterRun',frozen['runInput'])
        self.assertIsNone(store.row(self.f.sid)['thread_id']);self.assertIsNone(get_run(store,run['id'])['turn_id'])
        for changed in ({'runId':uid(),'nativeSessionId':self.f.native},{'runId':run['id'],'nativeSessionId':uid()}):
            with self.assertRaises(ProjectFault):messages.accept(self.f.sid,self.f.message_input()|{'afterRun':changed},self.f.providers)
        with self.assertRaises(ProjectFault):messages.accept(self.f.sid,data|{'afterRun':target|{'runId':uid()}},self.f.providers)
        self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0],1)
        self.assertEqual(store.db.execute('SELECT count(*) FROM session_messages').fetchone()[0],1)

    async def test_source_must_end_before_fifo_dispatch_and_original_ids_stay_separate(self):
        store,run,config,worker,lease,target=self.source();data,receipt,frozen=self.waiting(store,target)
        later=self.f.message_input();Messages(store).accept(self.f.sid,later,self.f.providers)
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,frozen)
        host=Host({'projects':str(self.f.projects),'r4os':str(self.f.r4os),'providers':str(self.f.providers),'uid':os.getuid(),'maxActiveRuns':2})
        host.inboxes.add(('project',self.f.pid,self.f.sid));host.launch_admitted=AsyncMock()
        await host.dispatch_queues();host.launch_admitted.assert_not_awaited()
        self.end(store,run,worker,lease);validate_queue(store,self.f.sid,frozen)
        await host.dispatch_queues();host.launch_admitted.assert_awaited_once()
        first=host.launch_admitted.await_args.args[1]
        self.assertNotEqual(first['id'],run['id'])
        new=get_run(store,first['id']);self.assertEqual(new['request_id'],data['requestId'])
        self.assertEqual(json.loads(new['config'])['engine']['claude']['nativeSessionId'],self.f.native)
        self.assertEqual(Messages(store).receipt(self.f.sid,data['requestId'])['state'],'dispatching')
        self.assertEqual(Messages(store).receipt(self.f.sid,later['requestId'])['state'],'queued')
        await host.dispatch_queues();host.launch_admitted.assert_awaited_once()
        self.assertEqual(json.loads(get_run(store,run['id'])['config']),config)

    async def test_stop_needs_a_later_human_continue_and_duplicate_control_does_not_reauthorize(self):
        store,run,config,worker,lease,target=self.source();data,_,frozen=self.waiting(store,target)
        early,_=self.resume(store);self.end(store,run,worker,lease,'interrupted')
        self.assertTrue(Messages(store).snapshot(self.f.sid)['held'])
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,frozen)
        Messages(store).control(self.f.sid,early,self.f.providers)
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,frozen)
        command,result=self.resume(store);validate_queue(store,self.f.sid,frozen)
        original=dict(store.db.execute('SELECT * FROM claude_wait_resumes WHERE message_id=?',(data['requestId'],)).fetchone())
        self.assertEqual(Messages(store).control(self.f.sid,command,self.f.providers),result)
        self.assertEqual(dict(store.db.execute('SELECT * FROM claude_wait_resumes WHERE message_id=?',(data['requestId'],)).fetchone()),original)
        self.assertEqual(Messages(store).receipt(self.f.sid,data['requestId'])['state'],'queued')
        with store.db:store.db.execute('UPDATE claude_wait_resumes SET command=? WHERE message_id=?',(encode(command|{'action':'cancel'}),data['requestId']))
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,frozen)

    async def test_unknown_or_changed_source_remains_protected_after_explicit_continue(self):
        store,run,config,worker,lease,target=self.source();data,_,frozen=self.waiting(store,target)
        self.end(store,run,worker,lease,'unknown');self.resume(store)
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,frozen)
        self.assertIsNone(public_target(store,get_run(store,run['id'])))
        self.assertEqual(Messages(store).receipt(self.f.sid,data['requestId'])['afterRun'],target)
        with self.assertRaises(ProjectFault):Messages(store).accept(self.f.sid,self.f.message_input()|{'afterRun':target},self.f.providers)

    async def test_restart_holds_unsent_waiting_and_cancellation_preserves_original_receipt(self):
        store,run,config,worker,lease,target=self.source();data,_,frozen=self.waiting(store,target)
        self.end(store,run,worker,lease);messages=Messages(store);messages.recover()
        host=Host({'projects':str(self.f.projects),'r4os':str(self.f.r4os),'providers':str(self.f.providers),'uid':os.getuid(),'maxActiveRuns':2})
        host.inboxes.add(('project',self.f.pid,self.f.sid));host.launch_admitted=AsyncMock()
        await host.dispatch_queues();host.launch_admitted.assert_not_awaited()
        self.assertTrue(messages.snapshot(self.f.sid)['held'])
        command={'requestId':uid(),'revision':messages.snapshot(self.f.sid)['revision'],'action':'cancel','messageId':data['requestId']}
        messages.control(self.f.sid,command,self.f.providers)
        self.assertEqual(messages.receipt(self.f.sid,data['requestId'])['state'],'cancelled')
        self.assertEqual(messages.receipt(self.f.sid,data['requestId'])['afterRun'],target)
        messages.recover();await host.dispatch_queues();host.launch_admitted.assert_not_awaited()
        self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0],1)

    async def test_changed_saved_target_cannot_be_admitted_or_rebound(self):
        store,run,config,worker,lease,target=self.source();data,_,frozen=self.waiting(store,target)
        self.end(store,run,worker,lease)
        altered={**frozen,'afterRun':target|{'runId':uid()}}
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,altered)
        with store.db:store.db.execute('UPDATE runs SET worker=? WHERE id=?',(encode(worker|{'birth':'changed-generation'}),run['id']))
        with self.assertRaises(ProjectFault):validate_queue(store,self.f.sid,frozen)
        self.assertEqual(Messages(store).row(self.f.sid,data['requestId'])['frozen'],encode(frozen))
