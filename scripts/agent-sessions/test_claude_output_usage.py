"""Final stream counters, immutable replay and scoped deletion retention."""
import json
import os
import unittest
from unittest.mock import AsyncMock,patch
import uuid

from claude_input_usage import InputUsage
from host import Host
from session_delete import preview,delete,resume,original
from stats_store import Source,read
from store import ProjectFault
import test_claude_input_usage as fixtures


class ClaudeOutputUsage(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.ClaudeInputUsage.setUp
    tearDown=fixtures.ClaudeInputUsage.tearDown
    open=fixtures.ClaudeInputUsage.open
    worker=fixtures.ClaudeInputUsage.worker
    message=fixtures.ClaudeInputUsage.message

    def stream(self,usage,w,message,outputs=(7,),stop=True,terminal=True):
        base={'type':'stream_event','session_id':w.config['engine']['claude']['nativeSessionId']}
        usage.notify(base|{'event':{'type':'message_start','message':{'id':message['message']['id']}}})
        usage.notify(message)
        for index,output in enumerate(outputs):usage.notify(base|{'event':{'type':'message_delta','usage':{'output_tokens':output},
            'delta':{'stop_reason':'end_turn' if terminal and index==len(outputs)-1 else None}}})
        if stop:usage.notify(base|{'event':{'type':'message_stop'}})

    async def test_final_output_and_total_are_once_per_response_even_after_resume(self):
        with self.open() as store:
            w=self.worker(store);message=self.message(w);usage=InputUsage(w)
            self.stream(usage,w,message,(2,7));usage.notify(message);usage.finish()
            self.assertEqual(read(self.projects)['tokens']['input'],'92')
            self.assertEqual(read(self.projects)['tokens']['output'],'7')
            self.assertEqual(read(self.projects)['tokens']['total'],'99')
            w.run_id=str(uuid.uuid4());replay=InputUsage(w);self.stream(replay,w,message);replay.finish()
            Source(store).flush(include_acknowledged=True)
            self.assertEqual(read(self.projects)['tokens']['total'],'99')
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM claude_output_usage').fetchone()[0],1)
            audit=store.db.execute('SELECT payload FROM claude_output_usage').fetchone()[0]
            self.assertNotIn('999999',audit);self.assertNotIn('Owned response text',audit)
            self.assertIsNone(read(self.projects)['tokens']['reasoningOutput'])

    async def test_missing_final_zero_and_unfinished_counts_are_distinct(self):
        with self.open() as store:
            w=self.worker(store);usage=InputUsage(w)
            zero=self.message(w,'msg_owned_zero_output');zero['message']['usage']={field:0 for field in
                ('input_tokens','cache_creation_input_tokens','cache_read_input_tokens')}
            self.stream(usage,w,zero,(0,))
            self.stream(usage,w,self.message(w,'msg_owned_missing_tail'),(4,None))
            self.stream(usage,w,self.message(w,'msg_owned_nonterminal_stop'),(13,),terminal=False)
            self.stream(usage,w,self.message(w,'msg_owned_unfinished_tail'),(9,),stop=False)
            usage.finish()
            self.assertEqual(read(self.projects)['tokens']['output'],'0')
            self.assertEqual(read(self.projects)['tokens']['total'],'0')
            self.assertTrue(read(self.projects)['coverage']['hasGaps'])
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM claude_output_usage').fetchone()[0],1)

    async def test_conflicts_foreign_stream_and_invalid_counters_keep_original(self):
        with self.open() as store:
            w=self.worker(store);message=self.message(w);usage=InputUsage(w)
            self.stream(usage,w,message);usage.finish()
            conflict=InputUsage(w);self.stream(conflict,w,message,(8,));conflict.finish()
            for index,outputs in enumerate([(8,3),(True,),(-1,),(2**53,),(1.5,)]):
                self.stream(usage,w,self.message(w,'msg_owned_bad_output_'+str(index)),outputs)
            foreign=self.message(w,'msg_owned_foreign_stream')
            usage.notify({'type':'stream_event','event':{'type':'message_start','message':{'id':foreign['message']['id']}}})
            usage.notify(foreign)
            usage.notify({'type':'stream_event','session_id':str(uuid.uuid4()),'event':{'type':'message_delta','usage':{'output_tokens':100}}})
            usage.notify({'type':'stream_event','session_id':w.config['engine']['claude']['nativeSessionId'],'event':{'type':'message_stop'}})
            usage.finish();Source(store).flush(include_acknowledged=True)
            self.assertEqual(read(self.projects)['tokens']['output'],'7')
            self.assertEqual(read(self.projects)['tokens']['total'],'99')
            self.assertTrue(read(self.projects)['coverage']['hasGaps'])

    async def test_actual_session_cleanup_preserves_pending_numeric_output(self):
        with self.open() as store:
            w=self.worker(store);usage=InputUsage(w);self.stream(usage,w,self.message(w))
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM claude_output_usage').fetchone()[0],1)
            from stats_lifecycle import preserve_pending
            with patch('stats_lifecycle.Source.flush',side_effect=ProjectFault('Owned unavailable global store',503)):
                self.assertEqual(preserve_pending(self.projects,store.directory/'Sessions.sqlite'),2)
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        with patch('session_delete.unit_states',new=AsyncMock(return_value=False)):
            view=await preview(host,'project',self.pid,self.sid);self.assertTrue(view['allowed'],view)
            data={'requestId':str(uuid.uuid4()),'revision':view['revision'],'scopeHash':view['scopeHash'],'confirmName':view['name']}
            await delete(host,'project',self.pid,self.sid,data)
            await resume(host,'project',self.pid,self.sid,data['requestId'])
        with self.open() as store:
            self.assertEqual(original(store,self.sid,data['requestId'])['state'],'deleted')
            self.assertFalse(store.db.execute('SELECT 1 FROM claude_output_usage').fetchone())
            self.assertFalse(store.db.execute('SELECT 1 FROM claude_input_usage').fetchone())
        pending=list((self.projects/'.studio/statistics/Pending').glob('*.json'));self.assertEqual(len(pending),2)
        for path in pending:
            value=json.loads(path.read_text());self.assertNotIn(self.sid,json.dumps(value));self.assertNotIn('msg_owned',json.dumps(value))
        from stats_lifecycle import flush_pending
        self.assertEqual(flush_pending(self.projects),2)
        self.assertEqual(read(self.projects)['tokens']['input'],'92')
        self.assertEqual(read(self.projects)['tokens']['output'],'7')
        self.assertEqual(read(self.projects)['tokens']['total'],'99')


if __name__=='__main__':unittest.main()
