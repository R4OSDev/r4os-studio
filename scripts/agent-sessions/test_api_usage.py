"""API provenance, numeric retention and missing usage in owned session stores."""
import json
import shutil
import unittest
import uuid

from api_provider_store import ApiProviders
from profile import CODEX_VERSION,CODEX_SHA256
from session_store import encode
from stats_store import Source,read,hashed
from usage_stats import Usage
import test_runs as fixtures

def request():return str(uuid.uuid4())


class ApiUsageTests(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open

    def ready(self,store,protocol='chat-completions'):
        self.providers.chmod(0o700)
        self.api=ApiProviders(self.providers)
        self.connection=self.api.mutate('create',None,{'requestId':request(),'name':'Own API usage','kind':'local','server':'ollama',
            'baseUrl':'http://127.0.0.1:11434/v1','protocol':protocol,'auth':'bearer','key':'only-owned-api-usage-key'})['provider']
        self.thread=request();self.run=request();self.turn='owned-turn'
        engine={'profile':json.loads(store.row(self.sid)['engine'])['profile'],'version':CODEX_VERSION,'sha256':CODEX_SHA256,'api':{'providerId':self.connection['id'],
            'baseUrl':self.connection['baseUrl'],'protocol':protocol,'server':'ollama'}}
        config={'apiRunId':self.run,'apiProvider':{k:self.connection[k] for k in ('id','kind','baseUrl','protocol','auth','server','revision','credentialRevision')},
            'engine':engine,'model':'owned/exact-model'}
        with store.db:
            settings=json.loads(store.row(self.sid)['settings'])
            settings.update(providerId=self.connection['id'],model='owned/exact-model',effort='none',webSearchEnabled=False,imageGenerationEnabled=False,fastMode=False)
            store.db.execute('UPDATE sessions SET thread_id=?,engine=?,settings=? WHERE id=?',(self.thread,encode(engine),encode(settings),self.sid))
            store.db.execute("INSERT INTO runs VALUES (?,?,?,'hash','completed',0,?,?,'{}',NULL,'now','now')",
                (self.run,self.sid,request(),encode(config),self.turn))
        return config

    def wire(self,store,response,values):
        from api_usage import wire_receipts
        has=store.db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_api_wire'").fetchone()
        ordinal=store.db.execute('SELECT COUNT(*) FROM statistic_api_wire WHERE run_id=?',(self.run,)).fetchone()[0]+1 if has else 1
        wire_receipts(store,self.sid,self.run,[{'ordinal':ordinal,'responseId':response,'usage':values}])

    def test_response_origin_joins_original_receipt_without_changing_its_spend_key(self):
        with self.open() as store:
            self.ready(store);usage=Usage(store,self.sid)
            self.wire(store,'local-response',{'total_tokens':13,'input_tokens':10,'output_tokens':3,'cached_input_tokens':2,'reasoning_output_tokens':0})
            values={'totalTokens':13,'inputTokens':10,'outputTokens':3,'cachedInputTokens':2,'reasoningOutputTokens':0}
            self.assertTrue(usage.ingest(self.thread,self.turn,'local-response',values,True,self.run))
            self.assertTrue(usage.ingest(self.thread,self.turn,'local-response',{'total_tokens':13,'input_tokens':10,
                'output_tokens':3,'cached_input_tokens':2,'reasoning_output_tokens':0},run_id=self.run))
            Source(store).flush();Source(store).flush(include_acknowledged=True)
            rows=store.db.execute('SELECT * FROM statistic_api_origins').fetchall();self.assertEqual(len(rows),1)
            origin=json.loads(rows[0]['origin'])
            self.assertEqual(rows[0]['key'],hashed({'source':'codex-response-v1','runtime':CODEX_SHA256,'thread':self.thread,'response':'local-response'}))
            self.assertEqual(origin['providerId'],self.connection['id']);self.assertEqual(origin['protocol'],'chat-completions')
            self.assertEqual(origin['responseIdKind'],'local-transport');self.assertEqual(origin['adapter'],'studio-chat-v1')
            self.assertNotIn('only-owned-api-usage-key',json.dumps(origin))
            result=read(self.projects);self.assertEqual(result['tokens']['total'],'13');self.assertEqual(result['tokens']['cachedInput'],'2')
            self.assertEqual(result['tokens']['reasoningOutput'],'0');self.assertNotIn(self.connection['id'],json.dumps(result))
            self.assertIsNone(result['tokens']['cacheWrite'])

    def test_missing_partial_and_conflicting_usage_never_invent_tokens_or_duplicate_credit(self):
        with self.open() as store:
            self.ready(store,'responses');usage=Usage(store,self.sid)
            self.wire(store,'missing',None);self.wire(store,'partial',{'input_tokens':5})
            self.assertFalse(usage.ingest(self.thread,self.turn,'missing',{'totalTokens':0,'inputTokens':0,'outputTokens':0},True,self.run))
            Source(store).flush();self.assertIsNone(read(self.projects)['tokens']['total'])
            usage.ingest(self.thread,self.turn,'partial',{'inputTokens':5},True,self.run);Source(store).flush()
            result=read(self.projects);self.assertIsNone(result['tokens']['total']);self.assertEqual(result['tokens']['input'],'5')
            origin=json.loads(store.db.execute('SELECT origin FROM statistic_api_origins').fetchone()[0])
            self.assertEqual(origin['responseIdKind'],'provider');self.assertEqual(origin['adapter'],'studio-responses-v1')
            self.assertTrue(usage.ingest(self.thread,self.turn,'partial',{'inputTokens':99},True,self.run))
            Source(store).flush();self.assertEqual(read(self.projects)['tokens']['input'],'5');self.assertTrue(read(self.projects)['coverage']['hasGaps'])

    def test_actual_sqlite_restore_reuses_existing_receipts_and_original_private_origins(self):
        with self.open() as store:
            self.ready(store);self.wire(store,'original',{'total_tokens':13,'input_tokens':10,'output_tokens':3})
            Usage(store,self.sid).ingest(self.thread,self.turn,'original',{'totalTokens':13,'inputTokens':10,'outputTokens':3},True,self.run)
            Source(store).flush();database=store.directory/'Sessions.sqlite';aggregate=self.projects/'.studio/statistics/Statistics.sqlite'
            before=store.db.execute('SELECT * FROM statistic_api_origins').fetchone();origin=tuple(before)
        source_backup=self.root/'source.sqlite';aggregate_backup=self.root/'aggregate.sqlite'
        shutil.copy2(database,source_backup);shutil.copy2(aggregate,aggregate_backup)
        shutil.copy2(source_backup,database);shutil.copy2(aggregate_backup,aggregate)
        with self.open() as store:
            Usage(store,self.sid).ingest(self.thread,self.turn,'original',{'total_tokens':13,'input_tokens':10,'output_tokens':3},run_id=self.run)
            Source(store).flush(include_acknowledged=True);Source(store).flush(include_acknowledged=True)
            self.assertEqual(read(self.projects)['tokens']['total'],'13')
            self.assertEqual(tuple(store.db.execute('SELECT * FROM statistic_api_origins').fetchone()),origin)

    def test_conflicting_frozen_origin_preserves_original_numbers_and_marks_gap(self):
        with self.open() as store:
            config=self.ready(store);usage=Usage(store,self.sid)
            self.wire(store,'original',{'total_tokens':13,'input_tokens':10,'output_tokens':3})
            values={'totalTokens':13,'inputTokens':10,'outputTokens':3}
            usage.ingest(self.thread,self.turn,'original',values,True,self.run)
            original=store.db.execute('SELECT origin FROM statistic_api_origins').fetchone()[0]
            config['apiProvider']['id']=request()
            with store.db:store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(config),self.run))
            usage.ingest(self.thread,self.turn,'original',values,True,self.run);Source(store).flush()
            self.assertEqual(read(self.projects)['tokens']['total'],'13');self.assertTrue(read(self.projects)['coverage']['hasGaps'])
            self.assertEqual(store.db.execute('SELECT origin FROM statistic_api_origins').fetchone()[0],original)

    def test_existing_subscription_receipts_and_schema_remain_provider_independent(self):
        with self.open() as store:
            thread=request()
            with store.db:store.db.execute('UPDATE sessions SET thread_id=? WHERE id=?',(thread,self.sid))
            Usage(store,self.sid).ingest(thread,'owned-turn','subscription-response',{'totalTokens':7},True)
            Source(store).flush();self.assertEqual(read(self.projects)['tokens']['total'],'7')
            self.assertIsNone(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_api_origins'").fetchone())
