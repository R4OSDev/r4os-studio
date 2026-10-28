"""Numeric lifetime receipts, scopes and corruption boundaries; no model work."""
import asyncio
import json
import unittest
from stats_store import Statistics,Source,read,scope,MAX_NUMBER
from host import Host
from store import ProjectFault
import test_runs as fixtures

class StatisticsTests(unittest.TestCase):
    setUp=fixtures.Runs.setUp
    tearDown=fixtures.Runs.tearDown
    open=fixtures.Runs.open

    def test_receipt_reconciliation_deduplicates_and_serializes_large_lifetime_sum(self):
        with self.open() as store:
            source=Source(store)
            for n in (1,2):source.put(self.sid,'tokens',{'response':str(n),'thread':'own-thread'},{'input':MAX_NUMBER,'output':0,'total':MAX_NUMBER})
            self.assertEqual(source.flush(),2);self.assertEqual(source.flush(include_acknowledged=True),2)
        global_value=read(self.projects)
        self.assertEqual(global_value['tokens']['total'],str(MAX_NUMBER*2));self.assertEqual(global_value['tokens']['output'],'0')
        owner={'type':'project','id':self.pid}
        self.assertEqual(read(self.projects,'project:'+scope(owner))['tokens'],global_value['tokens'])
        session=read(self.projects,'session:'+scope(owner,self.sid));self.assertEqual(session['tokens'],global_value['tokens']);self.assertNotIn('longestGoalMs',session)
        self.assertEqual(read(self.projects,'session:'+scope(owner,'foreign'))['tokens']['total'],None)

    def test_invalid_or_conflicting_receipts_preserve_original_and_corrupt_store(self):
        with self.open() as store:
            source=Source(store)
            for bad in (-1,True,MAX_NUMBER+1,float('nan')):
                with self.assertRaises(ProjectFault):source.put(self.sid,'tokens',{'response':'bad'},{'total':bad})
            receipt=source.put(self.sid,'tokens',{'response':'own'},{'total':7});source.flush()
            with self.assertRaises(ProjectFault):source.put(self.sid,'tokens',{'response':'own'},{'total':8})
            db=Statistics(self.projects,True)
            try:
                with self.assertRaises(ProjectFault):db.apply({**receipt,'values':{'total':8}})
                self.assertEqual(db.read()['tokens']['total'],'7');self.assertTrue(db.read()['coverage']['hasGaps'])
            finally:db.close()
        path=self.projects/'.studio/statistics/Statistics.sqlite';path.write_bytes(b'Owned corrupt storage')
        with self.assertRaises(ProjectFault):read(self.projects)
        self.assertEqual(path.read_bytes(),b'Owned corrupt storage')

    def test_legacy_missing_is_unknown_and_coordinator_checks_owner_and_session(self):
        self.assertIsNone(read(self.projects)['tokens']['total'])
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers)})
        value=asyncio.run(host.handle({'operation':'statistics','scope':'session','projectId':self.pid,'sessionId':self.sid}))
        self.assertNotIn('longestGoalMs',value)
        with self.assertRaises(ProjectFault):asyncio.run(host.handle({'operation':'statistics','scope':'session','projectId':self.pid,'sessionId':'00000000-0000-4000-8000-000000000000'}))
        self.assertFalse((self.projects/'.studio/statistics/Statistics.sqlite').exists())
