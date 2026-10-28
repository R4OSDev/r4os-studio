"""Response IDs are exact spend; native snapshots and opaque metadata are not."""
import json
import unittest
from unittest.mock import patch
import uuid
import test_runs as fixtures
from stats_store import Source,read,scope
from usage_stats import Usage
from session_store import encode
from profile import CODEX_VERSION,CODEX_SHA256

class UsageTests(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open
    def ready(self,store):
        thread=str(uuid.uuid4())
        with store.db:store.db.execute('UPDATE sessions SET thread_id=?,engine=? WHERE id=?',(thread,encode({'version':CODEX_VERSION,'sha256':CODEX_SHA256}),self.sid))
        return thread
    def test_multiple_responses_turns_replays_and_subsets_count_once(self):
        with self.open() as store:
            thread=self.ready(store);usage=Usage(store,self.sid)
            for response,turn in [('a','turn1'),('b','turn1'),('c','turn2')]:
                usage.ingest(thread,turn,response,{'totalTokens':10,'inputTokens':7,'outputTokens':3,'cachedInputTokens':2,'reasoningOutputTokens':1,'usageMetadata':{'amount':99999}},True)
            usage.ingest(thread,'turn1','a',{'total_tokens':10,'input_tokens':7,'output_tokens':3,'cached_input_tokens':2,'reasoning_output_tokens':1})
            Source(store).flush();Source(store).flush(include_acknowledged=True)
            session=read(self.projects,'session:'+scope({'type':'project','id':self.pid},self.sid))
            self.assertEqual(session['tokens']['total'],'30');self.assertEqual(session['tokens']['input'],'21');self.assertEqual(session['tokens']['cachedInput'],'6')
            self.assertEqual(read(self.projects)['tokens'],session['tokens']);self.assertNotIn('amount',json.dumps(session));self.assertNotIn('usageMetadata',json.dumps(session))
    def test_missing_and_conflicting_usage_keep_original_without_estimation(self):
        with self.open() as store:
            thread=self.ready(store);usage=Usage(store,self.sid)
            usage.ingest(thread,'turn1','missing',None);Source(store).flush()
            self.assertIsNone(read(self.projects)['tokens']['total'])
            usage.ingest(thread,'turn1','a',{'totalTokens':10,'inputTokens':7,'outputTokens':3},True)
            self.assertFalse(usage.ingest(thread,'turn1','a',{'totalTokens':99},True));Source(store).flush()
            self.assertEqual(read(self.projects)['tokens']['total'],'10');self.assertTrue(read(self.projects)['coverage']['hasGaps'])
    def test_bounded_native_backfill_ignores_snapshots_and_foreign_rollouts(self):
        with self.open() as store:
            thread=self.ready(store);root=store.directory/self.sid/'Codex/native/2026';root.mkdir(parents=True)
            path=root/('rollout-'+thread+'.jsonl')
            record={'type':'token_usage_record','payload':{'thread_id':thread,'session_id':thread,'turn_id':'own-turn','response_id':'own-response','usage':{'input_tokens':5,'output_tokens':2,'total_tokens':7}}}
            lines=[{'type':'session_meta','payload':{'id':thread}}, {'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'total_tokens':99999}}}},record]
            path.write_text(''.join(json.dumps(line)+'\n' for line in lines))
            usage=Usage(store,self.sid);self.assertEqual(usage.scan(),1);self.assertEqual(usage.scan(),0)
            with path.open('a') as file:file.write(json.dumps(record)+'\n')
            self.assertEqual(usage.scan(),1);Source(store).flush();self.assertEqual(read(self.projects)['tokens']['total'],'7')
            path.write_text(json.dumps({'type':'session_meta','payload':{'id':'foreign'}})+'\n'+json.dumps(record)+'\n')
            self.assertEqual(usage.scan(),0);self.assertEqual(read(self.projects)['tokens']['total'],'7')
