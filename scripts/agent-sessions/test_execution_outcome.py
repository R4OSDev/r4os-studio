"""A missing exit status must not turn a confirmed status read into an unknown effect."""
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import uuid

sys.path.append(str(Path(__file__).resolve().parents[1] / 'project-development'))
from development_tools import DevelopmentTools
from goal_store import Goals
from profile import COMPLETION_PROFILE
from run_store import get_run
from session_store import encode
import test_goal_control as controls


def closed_execution(worker, owner_run=None):
    job = {'id': str(uuid.uuid4()), 'kind': 'execution', 'state': 'unknown', 'phase': 'guest_completed',
        'projectId': worker.manifest['projectId'], 'sessionId': worker.session_id,
        'agentRunId': owner_run or worker.run_id, 'executionId': str(uuid.uuid4()), 'deploymentId': str(uuid.uuid4()),
        'target': {'vmId': str(uuid.uuid4()), 'bootId': str(uuid.uuid4()), 'helperSha256': 'a' * 64},
        'settings': {'expectedExitCode': None, 'visualCriteria': 'A visible test scene'},
        'check': {'state': 'passed'}, 'completedAt': '2026-10-28T10:04:47+00:00', 'exitCode': None, 'error': None,
        'process': {'instanceId': 30, 'generation': '30', 'windowId': 1}}
    state = {**job['process'], 'state': 'completed', 'closeConfirmed': True, 'exitCode': None,
        'exitEvidenceUnavailable': True, 'outputIncomplete': True, 'stopReason': None}
    job['guestState'] = state
    intent = {key: job[key] for key in ('executionId', 'deploymentId', 'target', 'settings')}
    intent.update(schema=1, jobId=job['id'], state='intent')
    root = worker.store.workspace.parent / 'Development/ExecutionWork' / job['id']; root.mkdir(parents=True)
    receipts = {'intent.json': intent, 'started.json': {**intent, 'state': 'started', 'process': job['process']},
        'closed.json': {**intent, 'state': 'closed', 'completion': state,
            'cleanupReceipt': {'closed': True, 'serviceRemoved': True, 'watchdogRemoved': True}}}
    for name, value in receipts.items(): (root / name).write_text(encode(value))
    return job, root


class ExecutionOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.worker = SimpleNamespace(manifest={'projectId': str(uuid.uuid4())}, session_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()), store=SimpleNamespace(workspace=Path(self.tmp.name) / 'Workspace'))
        self.tool = DevelopmentTools(self.worker)

    async def test_confirmed_status_read_retains_unknown_job_and_original_bytes(self):
        job, root = closed_execution(self.worker); before = copy.deepcopy(job)
        originals = {path.name: path.read_bytes() for path in root.iterdir()}
        self.tool.request = AsyncMock(return_value={'job': job, 'evidence': [{'id': 'original-image'}]})
        result = await self.tool.call('read_development_job', {'jobId': job['id']}, 'read-original')
        self.assertFalse(result['success']); self.assertEqual(result['error'], 'exit_status_unavailable')
        page = json.loads(result['output']); self.assertEqual(page['job'], before)
        self.assertEqual(page['evidence'], [{'id': 'original-image'}])
        self.assertTrue(page['executionReceipt']['cleanupConfirmed'])
        self.assertFalse(page['executionReceipt']['exitStatusConfirmed'])
        self.assertEqual(page['executionReceipt']['receiptSha256'], hashlib.sha256(originals['closed.json']).hexdigest())
        self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, originals)
        self.tool.request.assert_awaited_once_with('read_job', id=job['id'], offset=0)

    async def test_incomplete_foreign_or_damaged_closure_keeps_unknown_protection(self):
        cases = ('missing', 'malformed', 'non-object', 'symlink', 'hardlink', 'cleanup', 'numeric-flag', 'generation', 'start-generation',
            'execution', 'intent-target', 'settings', 'project', 'session', 'running', 'timeout', 'exit-available', 'no-marker')
        for case in cases:
            with self.subTest(case=case):
                job, root = closed_execution(self.worker)
                closed = json.loads((root / 'closed.json').read_text())
                if case == 'missing': (root / 'closed.json').unlink()
                elif case == 'malformed': (root / 'closed.json').write_text('{')
                elif case == 'non-object': (root / 'closed.json').write_text('[]')
                elif case == 'symlink':
                    (root / 'closed.json').rename(root / 'other.json'); (root / 'closed.json').symlink_to(root / 'other.json')
                elif case == 'hardlink': (root / 'other.json').hardlink_to(root / 'closed.json')
                elif case == 'cleanup': closed['cleanupReceipt']['watchdogRemoved'] = False
                elif case == 'numeric-flag': closed['completion']['closeConfirmed'] = 1
                elif case == 'generation': closed['completion']['generation'] = '31'
                elif case == 'start-generation':
                    started = json.loads((root / 'started.json').read_text()); started['process']['generation'] = '31'
                    (root / 'started.json').write_text(encode(started))
                elif case == 'execution': closed['executionId'] = str(uuid.uuid4())
                elif case == 'intent-target':
                    intent = json.loads((root / 'intent.json').read_text()); intent['target']['bootId'] = str(uuid.uuid4())
                    (root / 'intent.json').write_text(encode(intent))
                elif case == 'settings': closed['settings']['expectedExitCode'] = 0
                elif case == 'project': job['projectId'] = str(uuid.uuid4())
                elif case == 'session': job['sessionId'] = str(uuid.uuid4())
                elif case == 'running': closed['completion']['state'] = 'running'
                elif case == 'timeout': job['guestState']['stopReason'] = closed['completion']['stopReason'] = 'timeout'
                elif case == 'exit-available': job['guestState']['exitCode'] = closed['completion']['exitCode'] = 0
                elif case == 'no-marker': del closed['completion']['exitEvidenceUnavailable']
                if case not in ('missing', 'malformed', 'non-object', 'symlink', 'hardlink'):
                    (root / 'closed.json').write_text(encode(closed))
                result = self.tool.result(job)
                self.assertEqual(result['error'], 'unknown'); self.assertNotIn('executionReceipt', json.loads(result['output']))

    async def test_exit_criterion_is_not_satisfied_by_confirmed_closure(self):
        job, root = closed_execution(self.worker)
        job['settings']['expectedExitCode'] = 0
        for name in ('intent.json', 'started.json', 'closed.json'):
            value = json.loads((root / name).read_text()); value['settings'] = job['settings']
            (root / name).write_text(encode(value))
        spec = importlib.util.spec_from_file_location('execution_checks_fixture', Path(__file__).resolve().parents[1] / 'project-development/checks.py')
        checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
        job['check'] = checks.evaluate(job['settings'], job['guestState'], b'')
        result = self.tool.result(job)
        self.assertEqual(result['error'], 'exit_status_unavailable')
        self.assertEqual(json.loads(result['output'])['job']['check']['state'], 'inconclusive')
        self.assertIsNone(json.loads(result['output'])['job']['exitCode'])

    async def test_legacy_read_preserves_explicit_uncertainty_and_malformed_results(self):
        job, _ = closed_execution(self.worker)
        original = {'success': False, 'error': 'unknown', 'output': encode({'job': job}),
            'development': {'jobId': job['id']}}
        for change in ({'partialChangesPossible': True}, {'output': '[]'}, {'output': '{'},
                {'output': encode({'job': {**job, 'id': str(uuid.uuid4())}})}):
            with self.subTest(change=change):
                result = {**original, **change}
                self.assertIs(self.tool.replay_read({'jobId': job['id']}, result), result)


class ExecutionGoalTests(unittest.IsolatedAsyncioTestCase):
    setUp = controls.GoalControlTests.setUp
    tearDown = controls.GoalControlTests.tearDown
    open = controls.GoalControlTests.open
    command = controls.GoalControlTests.command
    goal_worker = controls.GoalControlTests.goal_worker

    async def active_worker(self):
        worker, native = await self.goal_worker()
        worker.config['engine']['profile'] = COMPLETION_PROFILE
        worker.config['permissions']['studio.read_development_job'] = True
        await worker.goal_worker.before_resume(); await worker.goal_worker.activate()
        await worker.notify('turn/started', {'threadId': worker.thread_id, 'turn': {'id': 'test-turn'}})
        return worker, native

    def params(self, worker, job, call_id='read-closed'):
        return {'namespace': None, 'threadId': worker.thread_id, 'turnId': worker.turn_id,
            'tool': 'studio_read_development_job', 'callId': call_id, 'arguments': {'jobId': job['id']}}

    async def test_known_closure_keeps_goal_active_and_allows_following_calls(self):
        worker, native = await self.active_worker(); job, _ = closed_execution(worker)
        worker.development.request = AsyncMock(return_value={'job': job})
        for call_id in ('first-read', 'next-read'):
            result = await worker.tool(self.params(worker, job, call_id))
            self.assertEqual(json.loads(result['contentItems'][0]['text'])['error'], 'exit_status_unavailable')
        self.assertEqual(worker.development.request.await_count, 2)
        self.assertFalse(worker.stopping); self.assertFalse(worker.uncertain_effect); self.assertFalse(worker.done.is_set())
        self.assertEqual(native.goal['status'], 'active'); self.assertEqual(Goals(worker.store).snapshot(self.sid)['phase'], 'idle')
        self.assertEqual(get_run(worker.store, worker.run_id)['state'], 'running')
        self.assertEqual(worker.store.db.execute("SELECT state FROM tools WHERE call_id='first-read'").fetchone()[0], 'failed')

    async def test_legacy_unknown_read_is_reclassified_without_replay_or_rewriting_original(self):
        worker, native = await self.active_worker(); old_run = str(uuid.uuid4())
        job, _ = closed_execution(worker, old_run); params = self.params(worker, job)
        original = encode({'success': False, 'error': 'unknown', 'output': encode({'job': job}),
            'development': {'jobId': job['id'], 'kind': 'execution', 'state': 'unknown'}})
        hashed = hashlib.sha256(encode({'tool': params['tool'], 'arguments': params['arguments']}).encode()).hexdigest()
        with worker.store.db:
            worker.store.db.execute('INSERT INTO runs(id,session_id,request_id,payload_hash,state,busy,config,created_at) VALUES(?,?,?,?,?,0,?,?)',
                (old_run, worker.session_id, str(uuid.uuid4()), 'legacy', 'unknown', '{}', 'before'))
            worker.store.db.execute('INSERT INTO tools VALUES(?,?,?,?,?,?,?)',
                (old_run, params['callId'], params['tool'], hashed, 'unknown', encode(params['arguments']), original))
        worker.execute = AsyncMock(); worker.development.request = AsyncMock()
        for _ in range(2):
            result = await worker.tool(params)
            self.assertEqual(json.loads(result['contentItems'][0]['text'])['error'], 'exit_status_unavailable')
        worker.execute.assert_not_awaited(); worker.development.request.assert_not_awaited()
        row = worker.store.db.execute('SELECT state,result FROM tools WHERE run_id=?', (old_run,)).fetchone()
        self.assertEqual(tuple(row), ('unknown', original)); self.assertEqual(get_run(worker.store, old_run)['state'], 'unknown')
        self.assertFalse(worker.stopping); self.assertEqual(native.goal['status'], 'active')

    async def test_missing_close_receipt_still_stops_and_pauses_goal(self):
        worker, native = await self.active_worker(); job, root = closed_execution(worker)
        (root / 'closed.json').unlink(); worker.development.request = AsyncMock(return_value={'job': job})
        result = await worker.tool(self.params(worker, job))
        self.assertEqual(json.loads(result['contentItems'][0]['text'])['error'], 'unknown')
        await asyncio.wait_for(worker.stop_task, 1)
        self.assertTrue(worker.stopping); self.assertTrue(worker.uncertain_effect)
        self.assertEqual(native.goal['status'], 'paused'); self.assertEqual(Goals(worker.store).snapshot(self.sid)['phase'], 'unknown')
