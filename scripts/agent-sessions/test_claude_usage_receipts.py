"""Native cumulative snapshots cannot silently become summed turn totals."""
import copy
import sqlite3
from types import SimpleNamespace
import unittest
import uuid

from claude_usage_receipts import record
from store import ProjectFault


class NativeUsageReceipts(unittest.TestCase):
    def test_original_binding_duplicate_conflict_cumulative_and_session_cleanup(self):
        db=sqlite3.connect(':memory:');self.addCleanup(db.close)
        db.execute('PRAGMA foreign_keys=ON');db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY)')
        sid=str(uuid.uuid4());native=str(uuid.uuid4());db.execute('INSERT INTO sessions VALUES (?)',(sid,));db.commit()
        worker=SimpleNamespace(store=SimpleNamespace(db=db),session_id=sid,run_id=str(uuid.uuid4()),
            row={'request_id':str(uuid.uuid4())},config={'engine':{'claude':{'nativeSessionId':native,'runtimeProfileId':'owned-runtime'}}})
        result={'uuid':str(uuid.uuid4()),'session_id':native,'subtype':'success',
            'usage':{'input_tokens':12,'output_tokens':4,'cache_creation_input_tokens':50,'cache_read_input_tokens':20},
            'modelUsage':{'owned-model':{'inputTokens':12,'outputTokens':4,'cacheCreationInputTokens':50,'cacheReadInputTokens':20,'costUSD':0.02}}}
        saved=record(worker,result);self.assertFalse(saved['totalsQualified']);self.assertIsNone(saved['nativeTurnId'])
        self.assertEqual(record(worker,result),saved)
        bad=copy.deepcopy(result);bad['usage']['output_tokens']=5
        with self.assertRaises(ProjectFault):record(worker,bad)
        self.assertEqual(db.execute('SELECT count(*) FROM claude_usage_receipts').fetchone()[0],1)
        # A resumed result is another cumulative snapshot, never an additional
        # billed turn total. No statistics/lifetime counters are fabricated.
        worker.run_id=str(uuid.uuid4());worker.row['request_id']=str(uuid.uuid4())
        later=copy.deepcopy(result);later['uuid']=str(uuid.uuid4());later['modelUsage']['owned-model']['outputTokens']=9
        self.assertEqual(record(worker,later)['nativeCumulativeModelUsage']['owned-model']['outputTokens'],9)
        for field,value in [('modelUsage',{'owned-model':None}),('usage',{'input_tokens':True}),('session_id',str(uuid.uuid4()))]:
            bad={**later,field:value,'uuid':str(uuid.uuid4())}
            with self.assertRaises(ProjectFault):record(worker,bad)
        self.assertEqual(db.execute('SELECT count(*) FROM claude_usage_receipts').fetchone()[0],2)
        with db:db.execute('DELETE FROM sessions WHERE id=?',(sid,))
        self.assertEqual(db.execute('SELECT count(*) FROM claude_usage_receipts').fetchone()[0],0)
