"""Multiple native text blocks and repeated snapshots retain their own content."""
import json
import unittest
import uuid

from claude_worker import ClaudeWorker
from run_store import admit,get_run
from session_store import encode
import test_runs as fixtures


class NativeStream(unittest.IsolatedAsyncioTestCase):
    async def test_interleaved_blocks_and_repeated_snapshots_do_not_overwrite_or_duplicate_text(self):
        f=fixtures.Runs('test_concurrent_retry_snapshot_stop_and_replay');f.setUp();self.addCleanup(f.tearDown)
        native=str(uuid.uuid4())
        with f.open() as store:
            run,_=admit(store,f.sid,f.data,f.providers)
            config=json.loads(get_run(store,run['id'])['config'])
            config['engine'].update(kind='claude-code',claude={'nativeSessionId':native})
            store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(config),run['id']));store.db.commit()
        worker=ClaudeWorker({'projects':str(f.projects),'r4os':str(f.r4os),'projectId':f.pid,'runId':run['id']})
        self.addCleanup(worker.store.close)
        async def observe(value):
            await worker.observe({'identity':{'nativeSessionId':native},'native':value})
        async def stream(value):await observe({'type':'stream_event','event':value})
        await stream({'type':'message_start','message':{'id':'own-provider-message'}})
        for index,text in [(0,'First block'),(2,'Second block')]:
            await stream({'type':'content_block_start','index':index,'content_block':{'type':'text'}})
            await stream({'type':'content_block_delta','index':index,'delta':{'type':'text_delta','text':text}})
        async def snapshot(parts,ident=None):
            value={'type':'assistant','uuid':ident or str(uuid.uuid4()),'message':{'id':'own-provider-message',
                'content':[{'type':'text','text':text} for text in parts]}}
            await observe(value)
            return value
        first=await snapshot(['First block'])
        await observe(first)
        await snapshot(['First block','Second block'])
        values=[i for i in worker.store.history(f.sid)['items'] if i['type']=='assistant']
        self.assertEqual([i['text'] for i in values],['First block','Second block'])
        self.assertTrue(all(i['status']=='completed' for i in values))
        self.assertTrue(all(i['nativeOrigin']['nativeSessionId']==native and i['nativeOrigin']['nativeTurnId'] is None for i in values))
        await observe({'type':'rate_limit_event','rate_limit_info':{'status':'allowed_warning','utilization':0.75,
            'resetsAt':1793362800,'rateLimitType':'five_hour'}})
        quota=json.loads(worker.store.db.execute("SELECT payload FROM events WHERE kind='claudeQuota'").fetchone()[0])
        self.assertEqual(quota['usedPercent'],75);self.assertEqual(quota['studioSessionId'],f.sid)
        self.assertEqual(quota['providerId'],f.provider)
        self.assertNotEqual(get_run(worker.store,run['id'])['state'],'failed')
        with self.assertRaises(ValueError):
            await worker.observe({'identity':{'nativeSessionId':str(uuid.uuid4())},'native':{'type':'result'}})
        original={'success':True,'output':'Original screenshot captured.','image':{'id':'own-image'}}
        result=await worker.mcp_output(original)
        self.assertEqual(json.loads(result['content'][0]['text']),original)
        self.assertIn('does not confirm visual inspection',result['content'][1]['text'])
        self.assertFalse(result['isError'])
