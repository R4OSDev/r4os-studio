"""Original last/window semantics, source ordering and read-only recovery."""
import json
from types import SimpleNamespace
import unittest
import uuid

from profile import CODEX_VERSION,CODEX_SHA256
from run_store import admit,transition
from session_context import Context,read,saved
from session_store import encode
import test_runs as fixtures


class SessionContext(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.Runs('test_concurrent_retry_snapshot_stop_and_replay');self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown);self.store=self.enterContext(self.fixture.open())
        self.run,_=admit(self.store,self.fixture.sid,self.fixture.data,self.fixture.providers)
        self.config=json.loads(self.store.db.execute('SELECT config FROM runs WHERE id=?',(self.run['id'],)).fetchone()[0])
        self.config['engine'].update(version=CODEX_VERSION,sha256=CODEX_SHA256);self.config['contextProtocol']=1
        self.store.db.execute('UPDATE sessions SET thread_id=?,engine=? WHERE id=?',('owned-thread',encode(self.config['engine']),self.fixture.sid))
        self.store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(self.config),self.run['id']));self.store.db.commit()
        self.worker=SimpleNamespace(store=self.store,session_id=self.fixture.sid,run_id=self.run['id'],config=self.config,thread_id='owned-thread')
        self.context=Context(self.worker)
        self.context.native({'thread':{'id':'owned-thread'},'model':'actual-native-model','modelProvider':'openai'})
        self.start('owned-turn')

    def start(self,turn):self.context.notify('turn/started',{'threadId':'owned-thread','turn':{'id':turn}})

    def measure(self,used=500,capacity=1000,**changes):
        data={'threadId':'owned-thread','turnId':'owned-turn','tokenUsage':{'total':{'totalTokens':9999999},
            'last':{'totalTokens':used,'inputTokens':400,'cachedInputTokens':300,'outputTokens':100,'reasoningOutputTokens':80},'modelContextWindow':capacity}}
        data.update(changes);self.context.notify('thread/tokenUsage/updated',data);return saved(self.store,self.fixture.sid)

    def test_last_not_total_no_cache_double_count_threshold_zero_unknown_and_duplicate(self):
        result=self.measure();self.assertEqual(result['usedTokens'],500);self.assertEqual(result['usedRatio'],.5)
        self.assertEqual(result['remainingTokens'],500);self.assertEqual(result['model'],'actual-native-model')
        self.assertEqual(result['last']['cachedInputTokens'],300)
        self.assertEqual(json.loads(self.store.db.execute("SELECT payload FROM events WHERE kind='context' ORDER BY seq DESC LIMIT 1").fetchone()[0]),result)
        self.assertEqual(self.measure()['revision'],result['revision'])
        self.assertGreater(self.measure(501)['usedRatio'],.5)
        self.assertEqual(self.measure(0)['usedRatio'],0)
        result=self.measure(1001);self.assertEqual(result['overflowTokens'],1);self.assertEqual(result['remainingTokens'],0)
        for value in (None,0,-1,True,1000.5):
            with self.subTest(window=value):
                result=self.measure(capacity=value);self.assertEqual(result['state'],'unavailable');self.assertIsNone(result['usedRatio'])
        self.assertEqual(self.measure(used=True)['state'],'stale')

    def test_compaction_decrease_order_foreign_turn_session_and_earlier_worker(self):
        first=self.measure(800)
        self.context.notify('item/started',{'threadId':'owned-thread','turnId':'owned-turn','item':{'type':'contextCompaction'}})
        self.assertEqual(self.measure(100)['state'],'stale')
        self.context.notify('item/completed',{'threadId':'owned-thread','turnId':'owned-turn','item':{'type':'contextCompaction'}})
        result=self.measure(100);self.assertEqual(result['usedTokens'],100);self.assertGreater(result['revision'],first['revision'])
        self.assertEqual(self.measure(999,threadId='foreign-thread'),result)
        self.start('later-turn');self.start('owned-turn')  # Replayed old start cannot restore an old turn.
        self.assertEqual(self.measure(999),result)
        self.measure(700,turnId='later-turn')
        transition(self.store,self.run['id'],'completed')
        later,_=admit(self.store,self.fixture.sid,{**self.fixture.data,'requestId':str(uuid.uuid4())},self.fixture.providers)
        previous=saved(self.store,self.fixture.sid);self.measure(999,turnId='later-turn')
        self.assertEqual(saved(self.store,self.fixture.sid),previous)
        self.assertEqual(read(self.store,self.store.row(self.fixture.sid))['state'],'stale')  # Older worker protocol.
        self.assertNotEqual(later['id'],self.run['id'])

    def test_reload_preserves_snapshot_selection_change_never_uses_new_catalog_window(self):
        original=self.measure();row=self.store.row(self.fixture.sid)
        self.assertEqual(read(self.store,row),original)
        settings=json.loads(row['settings']);settings['model']='new-selection'
        self.store.db.execute('UPDATE sessions SET settings=? WHERE id=?',(encode(settings),self.fixture.sid));self.store.db.commit()
        result=read(self.store,self.store.row(self.fixture.sid));self.assertEqual(result['state'],'pending')
        self.assertEqual(result['requestedModel'],original['requestedModel']);self.assertEqual(result['capacityTokens'],1000)
        self.measure(999);self.assertEqual(saved(self.store,self.fixture.sid),original)
        self.store.db.execute('UPDATE sessions SET settings=? WHERE id=?',(row['settings'],self.fixture.sid));self.store.db.commit()
        self.context.native({'thread':{'id':'owned-thread'},'model':'different-native-model','modelProvider':'openai'})
        self.assertEqual(saved(self.store,self.fixture.sid)['state'],'pending')
        self.assertEqual(self.measure(200)['model'],'different-native-model')
        transition(self.store,self.run['id'],'unknown')
        self.assertEqual(read(self.store,self.store.row(self.fixture.sid))['state'],'stale')

    def test_unqualified_engine_empty_read_and_private_cleanup(self):
        before=self.store.db.total_changes
        self.assertEqual(read(self.store,self.store.row(self.fixture.sid))['state'],'unavailable')
        self.assertEqual(self.store.db.total_changes,before)
        self.worker.config['engine']={**self.config['engine'],'api':{'providerId':str(uuid.uuid4())}}
        self.measure();self.assertIsNone(saved(self.store,self.fixture.sid))
        self.worker.config['engine'].pop('api');self.measure()
        from session_delete import selections
        self.assertIn('session_context',[v[0] for v in selections(self.store.db,self.fixture.sid)])
