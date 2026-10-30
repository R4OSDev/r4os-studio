"""Original Play authority, native evidence, bounded steps and passive recovery."""
import copy
import asyncio
import hashlib
import json
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import AsyncMock,Mock,patch

from claude_goal import CONTINUE_TEXT, GoalJournal, digest, lost
from goal_store import Goals
from run_store import admit, get_run
from session_store import encode, now
from store import ProjectFault
import test_claude_messages as fixtures


class ClaudeGoal(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ClaudeMessages(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.open = self.fixture.open; self.sid = self.fixture.sid; self.native = self.fixture.native
        self.tick = 1000000000

    def accepted_play(self, store):
        """Owned public Save/Play intent path; no user account or inference."""
        from claude_goal_store import idle
        goals=Goals(store);request=str(uuid.uuid4());save=str(uuid.uuid4())
        goals.accept(self.sid,{'requestId':save,'revision':goals.snapshot(self.sid)['revision'],'action':'save',
            'objective':'Complete the owned bounded fixture and check it.'})
        self.assertEqual(idle(goals,self.sid,save)['state'],'confirmed')
        goals.accept(self.sid,{'requestId':request,'revision':goals.snapshot(self.sid)['revision'],'action':'play','sessionRevision':1})
        return request

    def prepare(self):
        store = self.enterContext(self.open())
        request = self.accepted_play(store)
        run, fresh = admit(store, self.sid, {'mode': 'goal', 'goalRequestId': request, 'requestId': request, 'revision': 1}, self.fixture.providers)
        self.assertTrue(fresh)
        config, meta, lease = self.fixture.opening(store, run)
        worker = SimpleNamespace(store=store, session_id=self.sid, run_id=run['id'], row=get_run(store, run['id']),
            config=config, credential_worker=meta, stopping=False, uncertain_effect=False)
        journal = GoalJournal(worker, monotonic=lambda: self.tick); journal.start()
        return worker, journal

    def frame(self, journal):
        step = journal.read()['steps'][-1]
        return {'native': {'type': 'user', 'isReplay': True, 'session_id': self.native},
            'identity': {'nativeType': 'user', 'studioRequestId': journal.spec['requestId'],
                'studioGoalStepId': step['inputId'], 'nativeSessionId': self.native,
                'nativeInputRequestIds': [step['inputId']], 'nativeMessageId': step['inputId'],
                'nativeInputReceiptKind': 'stdinEcho', 'nativeInputTextSha256': step['textSha256']}}

    def active(self, journal):
        journal.admitted({'admissionId': str(uuid.uuid4())})
        journal.submitted(journal.read()['steps'][-1]['inputId'])
        self.assertTrue(journal.acknowledge(self.frame(journal)))

    def native_result(self):
        return {'type': 'result', 'uuid': str(uuid.uuid4()), 'session_id': self.native, 'subtype': 'success', 'is_error': False}

    def test_original_play_freeze_and_duplicate_execution_never_restarts(self):
        worker, journal = self.prepare()
        self.assertNotIn('goalExecution', worker.config)
        self.assertEqual(journal.spec['source'], 'studio-claude')
        self.assertEqual(journal.spec['maxSteps'], 8)
        self.assertEqual(journal.spec['maxActiveSeconds'], 900)
        with self.assertRaises(ProjectFault): journal.start()
        tampered = copy.deepcopy(worker.config)
        worker.config['claudeGoalExecution']['objective'] = 'Another unapproved goal'
        with self.assertRaises(ProjectFault): journal.read()
        worker.config = tampered
        self.assertIsNone(worker.store.row(self.sid)['thread_id'])
        self.assertIsNone(Goals(worker.store).snapshot(self.sid)['goal']['tokensUsed'])
        with self.assertRaises(ProjectFault):
            Goals(worker.store).accept(self.sid, {'requestId': str(uuid.uuid4()), 'revision': 1, 'action': 'play', 'sessionRevision': 1})

    def test_native_ack_report_result_and_fresh_admission_are_all_required(self):
        worker, journal = self.prepare()
        early={'status':'continue','reason':'Before native ACK'}
        denied=journal.report(early,'own-report-early');self.assertFalse(denied['success'])
        metadata = self.frame(journal); metadata['identity']['nativeType'] = 'system'
        self.assertFalse(journal.acknowledge(metadata))
        self.active(journal)
        self.assertEqual(journal.report(early,'own-report-early'),denied)
        self.assertIsNone(journal.read()['steps'][-1]['report'])
        report = {'status': 'continue', 'reason': 'The first checked step is done; another owned step remains.'}
        first = journal.report(report, 'own-report-1'); self.assertTrue(first['success'])
        self.assertEqual(journal.report(report, 'own-report-1'), first)
        self.assertFalse(journal.report(report | {'status': 'complete'}, 'own-report-1')['success'])
        self.assertTrue(journal.result(self.native_result()))
        next_input = journal.next(); self.assertNotEqual(next_input, worker.row['request_id'])
        second = journal.read()['steps'][-1]
        self.assertEqual(second['origin'], 'auto-continuation')
        self.assertEqual(second['textSha256'], hashlib.sha256(CONTINUE_TEXT.encode()).hexdigest())
        with self.assertRaises(ProjectFault): journal.submitted(next_input)
        self.active(journal)
        # Replaying an old successful call returns its old receipt but cannot
        # create a report for the new step or authorize another continuation.
        self.assertEqual(journal.report(report, 'own-report-1'), first)
        self.assertIsNone(journal.read()['steps'][-1]['report'])
        journal.report({'status': 'complete', 'reason': 'The owned objective and checks are complete.'}, 'own-report-2')
        self.assertFalse(journal.result(self.native_result()))
        self.assertEqual(journal.read()['state'], 'closing')
        final = journal.finish(True); self.assertEqual(final['state'], 'complete')
        self.assertEqual(len(final['steps']), 2)
        self.assertEqual(journal.finish(True),final)

    def test_missing_native_input_receipt_cannot_complete_or_continue(self):
        worker, journal = self.prepare()
        journal.admitted({'admissionId': str(uuid.uuid4())})
        journal.submitted(worker.row['request_id'])
        self.assertFalse(journal.result(self.native_result()))
        self.assertEqual(journal.finish(True)['state'], 'unknown')
        with self.assertRaises(ProjectFault): journal.next()

    def test_unconfirmed_tool_intent_preserves_unknown_even_with_complete_report(self):
        worker,journal=self.prepare();self.active(journal)
        journal.report({'status':'complete','reason':'Own model claims completion.'},'own-report-with-open-effect')
        with worker.store.db:
            worker.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',
                (worker.run_id,'own-unconfirmed-effect','studio_write_file','a'*64,'intent',encode({'path':'own.c'})))
        self.assertFalse(journal.result(self.native_result()))
        self.assertEqual(journal.finish(True)['state'],'unknown')
        self.assertIsNone(worker.store.db.execute("SELECT result FROM tools WHERE call_id='own-unconfirmed-effect'").fetchone()[0])
        with self.assertRaises(ProjectFault):journal.next()

    def test_stream_closure_and_passive_recovery_cannot_promote_model_completion(self):
        worker,journal=self.prepare();self.active(journal)
        journal.report({'status':'complete','reason':'Own checked work complete.'},'own-unclosed-final-report')
        self.assertFalse(journal.result(self.native_result()))
        self.assertEqual(journal.finish(False)['state'],'unknown')
        original=journal.read();lost(worker.store,worker.run_id);self.assertEqual(journal.read(),original)
        with self.assertRaises(ProjectFault):journal.result(self.native_result())

    def test_stop_wins_after_report_and_native_success_does_not_imply_goal_completion(self):
        worker, journal = self.prepare(); self.active(journal)
        self.assertTrue(journal.report({'status': 'complete', 'reason': 'Own checked work complete.'}, 'own-final-report')['success'])
        journal.stop(); worker.stopping = True
        self.assertFalse(journal.result(self.native_result()))
        self.assertEqual(journal.finish(True)['state'], 'paused')
        with self.assertRaises(ProjectFault): journal.next()

    def test_time_bound_and_passive_lost_recovery_preserve_original_ledger(self):
        worker, journal = self.prepare(); self.active(journal)
        journal.report({'status': 'continue', 'reason': 'Useful owned work remains.'}, 'own-budget-report')
        self.tick += 900 * 1000000000
        self.assertFalse(journal.result(self.native_result()))
        self.assertEqual(journal.finish(True)['state'], 'budgetLimited')
        original = journal.read()
        lost(worker.store, worker.run_id)
        self.assertEqual(journal.read(), original)
        # A new writer cannot attach the same accepted Play after a restart.
        with self.assertRaises(ProjectFault): GoalJournal(worker).start()

    def test_native_stop_closes_admission_even_when_goal_ledger_is_unreadable(self):
        original,_=self.prepare()
        from claude_worker import ClaudeWorker
        worker=ClaudeWorker({'projects':str(self.fixture.projects),'r4os':str(self.fixture.r4os),
            'providers':str(self.fixture.providers),'projectId':self.fixture.pid,'sessionId':self.sid,
            'runId':original.run_id,'release':'own-bounded-stop-check'})
        self.addCleanup(worker.store.close)
        worker.claude_goal=SimpleNamespace(stop=Mock(side_effect=ProjectFault('Original ledger unavailable',409)))
        worker.broker=SimpleNamespace(stop_admission=Mock());worker.native=None
        with patch('worker.Worker._stop',new_callable=AsyncMock) as common_stop:
            asyncio.run(worker._stop())
            worker.broker.stop_admission.assert_called_once();common_stop.assert_awaited_once()
        self.assertTrue(worker.stopping);self.assertTrue(worker.uncertain_effect)


if __name__ == '__main__': unittest.main()
