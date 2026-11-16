"""Oversized instruction admission, atomic replacement and original run continuation."""
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from conversation import Conversation
import goal_keepalive
from goal_store import Goals
from model_transport import dumps
from project_agents import MAX_BYTES, read_at
from project_instruction_compaction import compact, replacement
from run_store import admit, get_run, transition
from session_store import encode
from store import ProjectFault
from studio_engine import engine
from studio_worker import StudioWorker
import test_runs


KEEP = 'Keep the SDK pinned. See Docs/Current.md.\n'
BEFORE = KEEP + 'Previously completed release log. ä\n' * 1000
AFTER = KEEP + 'Keep current test requirements.\n'


class InstructionCompaction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixture = test_runs.Runs()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.store = self.enterContext(fixture.open())
        self.sid = fixture.sid
        self.file = self.store.workspace / 'Agents.md'
        self.file.write_text(BEFORE)
        with self.store.db:
            self.store.db.execute('UPDATE sessions SET engine=? WHERE id=?', (encode(engine('project')), self.sid))
        self.received = []
        from api_provider_store import ApiProviders
        self.enterContext(patch.object(ApiProviders, 'reserve'))
        self.enterContext(patch.object(ApiProviders, 'claim', return_value=None))
        self.enterContext(patch.object(ApiProviders, 'validate_active'))
        self.enterContext(patch.object(ApiProviders, 'release'))
        self.enterContext(patch('api_models.freeze', side_effect=self.bind))

    def bind(self, store, sid, data, providers, config, original=None):
        config['apiProvider'] = {'id': self.fixture.provider, 'kind': 'local', 'protocol': 'responses',
            'baseUrl': getattr(self, 'url', 'http://127.0.0.1:1/v1'), 'auth': 'none', 'revision': 1,
            'credentialRevision': 0}
        config['apiModel'] = {'contextWindow': 1000000, 'reasoning': 'unsupported'}

    def accept(self, keepalive=None):
        data = {**self.fixture.data, 'requestId': str(uuid.uuid4())}
        if keepalive:
            data.update(requestId=keepalive['requestId'], text=keepalive['goal']['objective'])
        run, fresh = admit(self.store, self.sid, data, self.fixture.providers, keepalive=keepalive)
        self.assertTrue(fresh)
        return run['id']

    def operation(self, run_id, result, *, guard=True):
        row = get_run(self.store, run_id)
        run = SimpleNamespace(store=self.store, run_id=run_id, session_id=self.sid, config=json.loads(row['config']),
            goal_worker=SimpleNamespace(execution='fixture-goal', can_restart_model=lambda: guard),
            active=lambda: True, validate_lease=lambda: None, infer_once=AsyncMock(return_value=result))
        return run

    async def serve(self, replies):
        async def answer(reader, writer):
            try:
                header = (await reader.readuntil(b'\r\n\r\n')).decode()
                length = int(next(line.split(':', 1)[1] for line in header.splitlines()
                                  if line.lower().startswith('content-length:')))
                self.received.append(json.loads(await reader.readexactly(length)))
                value = {'type': 'response.completed', 'response': {'id': 'response-' + str(len(self.received)),
                    'status': 'completed', 'model': 'fixture', 'output': [
                        {'type': 'message', 'id': 'answer', 'content': [
                            {'type': 'output_text', 'text': replies[len(self.received) - 1]}]}]}}
                body = ('data: ' + dumps(value) + '\n\n').encode()
                writer.write((f'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                              f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode() + body)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(answer, '127.0.0.1', 0)
        self.addAsyncCleanup(server.wait_closed)
        self.addCleanup(server.close)
        self.url = f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1'

    async def run_worker(self, run_id):
        conversation = Conversation(self.store, self.sid)
        conversation.initialize({'type': 'fixture'})
        manifest = {'projects': str(self.fixture.projects), 'r4os': str(self.fixture.r4os),
                    'providers': str(self.fixture.providers), 'projectId': self.fixture.pid,
                    'runId': run_id, 'release': 'fixture'}
        await StudioWorker(manifest).run()
        row = get_run(self.store, run_id)
        self.assertEqual(row['state'], 'completed', row['error'])

    async def test_manual_send_infers_once_with_new_instructions_and_preserves_original(self):
        await self.serve([json.dumps({'text': AFTER}), 'Confirmed answer.'])
        run_id = self.accept()
        await self.run_worker(run_id)
        self.assertEqual(self.file.read_text(), AFTER)
        self.assertEqual(len(self.received), 2)
        prep, reply = self.received
        self.assertEqual(prep['model'], reply['model'])
        self.assertEqual(prep['tools'], [])
        self.assertEqual(json.loads(prep['input'][0]['content'])['source'], BEFORE)
        self.assertIn(AFTER, reply['instructions'])
        self.assertNotIn('Previously completed release log.', reply['instructions'])
        self.assertEqual(reply['input'][-1]['content'], self.fixture.data['text'])
        cfg = json.loads(get_run(self.store, run_id)['config'])
        self.assertEqual(cfg['projectInstructions']['text'], BEFORE)
        self.assertEqual(cfg['projectInstructions']['sha256'], hashlib.sha256(BEFORE.encode()).hexdigest())
        ops = [json.loads(row[0])['purpose'] for row in self.store.db.execute(
            'SELECT data FROM studio_model_calls WHERE run_id=? ORDER BY rowid', (run_id,))]
        self.assertEqual(ops, ['project-instructions', 'conversation'])

    async def test_goal_continues_with_updated_instructions_and_same_goal(self):
        self.file.write_text(KEEP)
        predecessor = self.accept()
        transition(self.store, predecessor, 'completed')
        goals = Goals(self.store)
        objective = 'Finish the existing Goal.'
        goal_keepalive.accept(goals, self.sid, {'requestId': str(uuid.uuid4()), 'revision': 0,
            'action': 'save', 'objective': objective})
        goal_keepalive.accept(goals, self.sid, {'requestId': str(uuid.uuid4()),
            'revision': goals.snapshot(self.sid)['revision'], 'action': 'play', 'sessionRevision': 1})
        execution = goal_keepalive.prepare(self.store, self.sid, predecessor)
        self.file.write_text(BEFORE)
        await self.serve([json.dumps({'text': AFTER}), 'Verified goal progress.'])
        run_id = self.accept(execution)
        goal_keepalive.admitted(self.store, self.sid, execution, run_id)
        await self.run_worker(run_id)
        self.assertEqual(self.file.read_text(), AFTER)
        goal = goal_keepalive.row(self.store, self.sid)
        self.assertTrue(goal['active'])
        self.assertEqual(goal['goal']['goalId'], execution['goal']['goalId'])
        self.assertEqual(self.received[1]['input'][-1]['content'], objective)
        self.assertIn(AFTER, self.received[1]['instructions'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM runs').fetchone()[0], 2)

    async def test_utf8_exact_limit_has_no_compaction(self):
        self.file.write_text('ä' * (MAX_BYTES // 2))
        run_id = self.accept()
        config = json.loads(get_run(self.store, run_id)['config'])
        self.assertNotIn('projectInstructionsCompaction', config)
        self.assertEqual(read_at(self.store.workspace, self.store.project)['text'].encode(), self.file.read_bytes())

    async def test_invalid_output_concurrent_change_and_stop_leave_file_intact(self):
        run_id = self.accept()
        result = {'content': [{'type': 'text', 'text': json.dumps({'text': 'ä' * MAX_BYTES})}],
                  'origin': {'studioRequestId': 'fixture'}}
        worker = self.operation(run_id, result)
        with self.assertRaisesRegex(ProjectFault, 'at most 32 KiB'):
            await compact(worker)
        self.assertEqual(self.file.read_text(), BEFORE)
        worker.infer_once.side_effect = ProjectFault('The fixture model failed.')
        with self.assertRaisesRegex(ProjectFault, 'fixture model failed'):
            await compact(worker)
        self.assertEqual(self.file.read_text(), BEFORE)

        async def concurrent(*args):
            self.file.write_text('Concurrent edit\n')
            return {**result, 'content': [{'type': 'text', 'text': json.dumps({'text': AFTER})}]}

        worker.infer_once.side_effect = concurrent
        with self.assertRaisesRegex(ProjectFault, 'changed while'):
            await compact(worker)
        self.assertEqual(self.file.read_text(), 'Concurrent edit\n')
        self.file.write_text(BEFORE)
        worker.infer_once.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await compact(worker)
        self.assertEqual(self.file.read_text(), BEFORE)

    async def test_unavailable_file_and_invalid_result_shape_are_rejected(self):
        other = Path(self.fixture.root) / 'outside'
        other.write_text(BEFORE)
        self.file.unlink()
        self.file.symlink_to(other)
        with self.assertRaises(ProjectFault):
            self.accept()
        self.assertEqual(other.read_text(), BEFORE)
        with self.assertRaises(ProjectFault):
            replacement({'content': [{'type': 'text', 'text': '{"text":"foo","extra":1}'}]})
