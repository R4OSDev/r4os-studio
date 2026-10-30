"""Own API queue/deletion fixtures; no service start, model or VM operation."""
import json
import os
import unittest
from unittest.mock import AsyncMock,patch

from api_catalog import Catalogs
from host import Host
from message_store import Messages
from session_delete import preview,delete,resume,original
from stats_store import Source,read
from usage_stats import Usage
from store import ProjectFault
import test_api_usage as usage_fixtures
from test_api_usage import request
import test_runs as fixtures


class ApiLifecycleTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    ready=usage_fixtures.ApiUsageTests.ready
    wire=usage_fixtures.ApiUsageTests.wire

    def host(self):
        control=patch('session_delete.unit_states',new=AsyncMock(return_value=False));control.start();self.addCleanup(control.stop)
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        host.active_unit=AsyncMock(return_value=False);host.launch_admitted=AsyncMock()
        return host

    async def test_unconfirmed_api_lease_blocks_session_and_provider_deletion_preserving_key(self):
        with self.open() as store:
            config=self.ready(store);rid=store.db.execute('SELECT request_id FROM runs WHERE id=?',(self.run,)).fetchone()[0]
        self.api.reserve(self.run,'project',self.pid,self.sid,rid,config)
        with self.api.connect(write=True) as db:db.execute("UPDATE leases SET state='unknown' WHERE run_id=?",(self.run,))
        host=self.host();result=await preview(host,'project',self.pid,self.sid)
        self.assertFalse(result['allowed']);self.assertTrue(any('API' in reason for reason in result['blockers']))
        data={'requestId':request(),'revision':1}
        pending=self.api.mutate('delete',self.connection['id'],data);self.assertEqual(pending['state'],'pending')
        with self.assertRaises(ProjectFault):self.api.mutate('delete',self.connection['id'],data,finish=True)
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM secrets.credentials').fetchone()[0],1)
        self.assertFalse((await preview(host,'project',self.pid,self.sid))['allowed'])

    async def test_confirmed_api_release_and_provider_delete_allow_named_session_cleanup_with_lifetime_retained(self):
        with self.open() as store:
            config=self.ready(store);rid=store.db.execute('SELECT request_id FROM runs WHERE id=?',(self.run,)).fetchone()[0]
            self.wire(store,'local-original',{'total_tokens':13,'input_tokens':10,'output_tokens':3})
            Usage(store,self.sid).ingest(self.thread,self.turn,'local-original',{'totalTokens':13,'inputTokens':10,'outputTokens':3},True,self.run)
            Source(store).flush()
        self.api.reserve(self.run,'project',self.pid,self.sid,rid,config)
        self.api.release(self.run,'project',self.pid,self.sid,rid,config)
        data={'requestId':request(),'revision':1}
        self.api.mutate('delete',self.connection['id'],data);self.api.mutate('delete',self.connection['id'],data,finish=True)
        host=self.host();view=await preview(host,'project',self.pid,self.sid);self.assertTrue(view['allowed'],view)
        command={'requestId':request(),'revision':view['revision'],'scopeHash':view['scopeHash'],'confirmName':view['name']}
        self.assertEqual((await delete(host,'project',self.pid,self.sid,command))['state'],'deleting')
        await resume(host,'project',self.pid,self.sid,command['requestId'])
        with self.open() as store:
            self.assertEqual(original(store,self.sid,command['requestId'])['state'],'deleted')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM statistic_api_origins').fetchone()[0],0)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM statistic_api_wire').fetchone()[0],0)
        self.assertEqual(read(self.projects)['tokens']['total'],'13')
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM secrets.credentials').fetchone()[0],0)

    async def test_rotation_holds_original_queue_and_restore_does_not_start_or_replace_its_worker(self):
        with self.open() as store:
            self.ready(store)
            Catalogs(self.providers).save_model(self.connection['id'],{'requestId':request(),'providerRevision':1,'catalogRevision':0,
                'model':{'id':'owned/exact-model','contextWindow':8192,'capabilities':{'text':'supported','functionTools':'supported','streaming':'supported','reasoning':'unsupported'}}})
            queued,_=Messages(store).accept(self.sid,{'requestId':request(),'revision':1,'mode':'queue','text':'Original owned queued input'},self.providers,
                {'nativeWebSearch':1,'environmentNotesSettings':1,'imageGenerationSettings':1})
            frozen=Messages(store).row(self.sid,queued['requestId'])['frozen'];before=store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
        self.api.mutate('update',self.connection['id'],{'requestId':request(),'revision':1,'key':'only-owned-rotated-key'})
        host=self.host();host.inboxes.add(('project',self.pid,self.sid));await host.dispatch_queues()
        host.launch_admitted.assert_not_awaited()
        with self.open() as store:
            inbox=Messages(store);self.assertTrue(inbox.snapshot(self.sid)['held'])
            self.assertEqual(inbox.row(self.sid,queued['requestId'])['frozen'],frozen)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],before)
            inbox.recover();self.assertTrue(inbox.snapshot(self.sid)['held'])
            inbox.control(self.sid,{'requestId':request(),'revision':inbox.snapshot(self.sid)['revision'],'action':'cancel','messageId':queued['requestId']},self.providers)
            self.assertEqual(inbox.receipt(self.sid,queued['requestId'])['state'],'cancelled')
        with self.api.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM secrets.credentials').fetchone()[0],1)
