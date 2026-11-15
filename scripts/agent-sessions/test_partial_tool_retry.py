"""Exercise partial tool streams over the direct worker and its real HTTP child."""
import asyncio
import json
import os
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from attachment_store import birth
from conversation import Conversation
from model_transport import ModelFault, ModelTransport, dumps
from provider_retry import ProviderRetry, snapshot
from run_store import get_run
from session_store import encode
from studio_worker import StudioWorker
from worker import Worker
import test_request_capture


TOOL = {'name': 'studio_read_file', 'description': 'Read a fixture file',
        'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}}
ARGUMENTS = {'path': 'module.R4MF'}
START = {'type': 'response.created', 'response': {'id': 'partial', 'output': []}}
ITEM = {'type': 'response.output_item.added', 'output_index': 1, 'item': {'id': 'fc_partial',
        'type': 'function_call', 'status': 'in_progress', 'call_id': 'partial-call', 'name': TOOL['name']}}
DELTA = {'type': 'response.function_call_arguments.delta', 'output_index': 1,
         'item_id': 'fc_partial', 'delta': '{"path":"module'}
REASONING = {'output_index': 0, 'item': {'type': 'reasoning', 'id': 'rs_fixture', 'summary': []}}
PARTIAL = [START, {**REASONING, 'type': 'response.output_item.added'},
           {**REASONING, 'type': 'response.output_item.done'}, ITEM, DELTA]


def responses_result(output, ident):
    return [{'type': 'response.completed', 'response': {'id': ident, 'status': 'completed',
             'model': 'own-model', 'output': output}}]


def http_stream(events, *, interrupted=False, tail=b''):
    payload = b''.join(b'data: ' + (dumps(event).encode() if not isinstance(event, str) else event.encode())
                       + b'\n\n' for event in events) + tail
    length = len(payload) + (128 if interrupted else 0)
    headers = (f'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: {length}\r\n'
               'Connection: close\r\n\r\n')
    return headers.encode() + payload


class PartialToolRetry(test_request_capture.CaptureFixture, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.received = []
        self.confirmed_calls = []
        self.timers = []
        self.text = []
        self.config = json.loads(get_run(self.store, self.run['id'])['config'])
        self.config.update(engine={'kind': 'studio'}, streamRetryProtocol=3, effort='none', model='own-model',
                           toolCatalog={'version': 2, 'tools': [TOOL['name']]})
        self.config['permissions']['studio.read_file'] = True
        self.turn = 'original-turn'
        worker_id = {'pid': os.getpid(), 'birth': birth(os.getpid()), 'release': 'local-fixture'}
        with self.store.db:
            self.store.db.execute('UPDATE runs SET state=?,turn_id=?,config=?,worker=? WHERE id=?',
                                  ('running', self.turn, encode(self.config), encode(worker_id), self.run['id']))
        self.goal = SimpleNamespace(execution='active-goal', active=True, current=lambda: {'tokenBudget': None},
                                    can_restart_model=lambda: True, boundary=AsyncMock(), instructions=lambda: '',
                                    missing_usage=lambda _: None, observe=lambda *args: None, pause=AsyncMock())
        self.messages = [{'role':'user','content':[{'type':'text','text':'Read the project manifest.'}]}]
        self.worker = SimpleNamespace(config=self.config, store=self.store, session_id=self.sid, run_id=self.run['id'],
            manifest={'release': 'local-fixture', 'providers': str(self.fixture.providers)}, model=None, operation=None,
            stopping=False, uncertain_effect=False, closing=False, done=asyncio.Event(), turn_id=self.turn,
            thread_id='original-thread', validate_lease=lambda: None, active=lambda: not self.worker.stopping,
            operations=self.operations, transport=lambda **_: self.model, context_results=SimpleNamespace(provenance=None),
            observe_limit=lambda error: None, goal_worker=self.goal, outcome='failed', items={}, round=0,
            execute=self.execute, tool_result=self.tool_result, declarations=lambda: [TOOL],
            message_worker=SimpleNamespace(boundary=lambda: False, messages=SimpleNamespace(waiting_after=lambda *_: False)))
        for name in ('infer', 'infer_once', 'response', 'cycle', 'receipt_id', 'validate_calls'):
            setattr(self.worker, name, MethodType(getattr(StudioWorker, name), self.worker))
        self.worker.bound_tool = MethodType(Worker.bound_tool, self.worker)
        self.worker.provider_retry = ProviderRetry(self.worker)
        self.addAsyncCleanup(self.worker.provider_retry.close)

    async def serve(self, replies, protocol='responses', first_reply_parsed=None):
        async def handle(reader, writer):
            try:
                header = (await reader.readuntil(b'\r\n\r\n')).decode()
                length = int(next(line.split(':', 1)[1] for line in header.splitlines()
                                  if line.lower().startswith('content-length:')))
                index = len(self.received) - offset
                self.received.append(await reader.readexactly(length))
                writer.write(replies[index])
                await writer.drain()
                if index == 0 and first_reply_parsed is not None:
                    await asyncio.wait_for(first_reply_parsed.wait(), 5)
            finally:
                writer.close()
                await writer.wait_closed()

        offset = len(self.received)
        server = await asyncio.start_server(handle, '127.0.0.1', 0)
        self.addAsyncCleanup(server.wait_closed)
        self.addCleanup(server.close)
        port = server.sockets[0].getsockname()[1]
        self.config['apiProvider'].update(protocol=protocol, baseUrl=f'http://127.0.0.1:{port}/v1',
                                         auth='none', contextWindow=1000000, reasoning='unsupported')
        self.model = ModelTransport(self.config['apiProvider'], 'own-model', chat_policy={'reasoning': 'none'})
        with self.store.db:
            self.store.db.execute('UPDATE runs SET config=? WHERE id=?', (encode(self.config), self.run['id']))

    async def execute(self, name, arguments, call_id):
        self.confirmed_calls.append((name, arguments, call_id))
        return {'success': True, 'output': 'Confirmed fixture manifest'}

    async def tool_result(self, result, image=None, call_id=None):
        return result

    async def record_text(self, text):
        self.text.append(text)

    async def fast_timer(self, seconds):
        self.timers.append(seconds)
        self.assertEqual(self.retry()['state'], 'waiting')
        self.assertTrue(self.model.closed_confirmed)

    async def infer(self):
        with patch('provider_retry.asyncio.sleep', self.fast_timer):
            return await self.worker.infer(self.messages, 'Fixture instructions', [TOOL], on_text=self.record_text)

    def retry(self):
        return snapshot(self.store, get_run(self.store, self.run['id']))

    def previous_receipt(self, result):
        with self.store.db:
            self.store.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,?)', (self.run['id'], 'previous-result',
                                  TOOL['name'], 'original-hash', 'completed', '{}', encode(result)))

    def tool_rows(self):
        return [tuple(row) for row in self.store.db.execute('SELECT call_id,state FROM tools ORDER BY rowid')]

    def operations_for_run(self):
        return [(row['request_id'], row['phase'], json.loads(row['data']))
                for row in self.store.db.execute('SELECT * FROM studio_model_calls ORDER BY rowid')]

    async def test_responses_retries_exact_input_and_executes_only_confirmed_tool(self):
        complete = {**ITEM['item'], 'id': 'fc_success', 'call_id': 'confirmed-call',
                    'status': 'completed', 'arguments': dumps(ARGUMENTS)}
        answer = {'type': 'message', 'id': 'answer', 'content': [{'type': 'output_text', 'text': 'Done.'}]}
        await self.serve([http_stream(PARTIAL, interrupted=True), http_stream(responses_result([complete], 'replay')),
                          http_stream(responses_result([answer], 'final'))])
        old_receipt = {'success': True, 'output': 'Original paired receipt'}
        self.previous_receipt(old_receipt)
        conversation = Conversation(self.store, self.sid)
        conversation.initialize({'type': 'local-fixture'})
        conversation.append(self.run['id'], 'user-input', 'user', self.messages[0]['content'], {})
        conversation.append(self.run['id'], 'old-call', 'assistant',
                            [{'type': 'tool_call', 'callId': 'old-call', 'name': TOOL['name'], 'arguments': ARGUMENTS}], {})
        conversation.append(self.run['id'], 'old-result', 'tool',
                            [{'type': 'tool_result', 'callId': 'old-call', 'result': old_receipt}], {})
        self.worker.conversation = conversation
        self.worker.context = SimpleNamespace(prepare=AsyncMock(side_effect=lambda *_: conversation.records()),
                                              report=lambda *_: None)
        self.goal.active = False
        self.goal.execution = None
        with patch('provider_retry.asyncio.sleep', self.fast_timer):
            await self.worker.cycle()
        self.assertEqual(self.worker.outcome, 'completed')
        self.assertEqual(self.timers, [60])
        self.assertEqual(len(self.received), 3)
        self.assertEqual(self.received[0], self.received[1])
        self.assertIn(b'Original paired receipt', self.received[1])
        self.assertIn(b'Confirmed fixture manifest', self.received[2])
        self.assertNotIn(b'partial-call', self.received[2])
        confirmed = self.worker.receipt_id('confirmed-call')
        self.assertEqual(self.confirmed_calls, [('read_file', ARGUMENTS, confirmed)])
        self.assertEqual(self.tool_rows(), [('previous-result', 'completed'), (confirmed, 'completed')])
        first, replay, final = self.operations_for_run()
        self.assertEqual((first[1], replay[1], final[1]), ('unknown', 'completed', 'completed'))
        self.assertEqual(first[2]['requestSha256'], replay[2]['requestSha256'])
        self.assertTrue(first[2]['error']['pendingToolStreamInterruption'])
        self.assertTrue(first[2]['processEnd']['confirmed'])
        self.assertEqual(self.retry()['state'], 'completed')

    async def test_chat_and_messages_partial_tool_arguments_can_retry(self):
        chat_delta = {'id': 'chat', 'choices': [{'index': 0, 'delta': {'tool_calls': [
            {'index': 0, 'id': 'tool-chat', 'function': {'name': TOOL['name'], 'arguments': DELTA['delta']}}]},
            'finish_reason': None}]}
        chat_done = {'id': 'chat-replay', 'choices': [{'index': 0, 'delta': {'content': 'OK'}, 'finish_reason': 'stop'}]}
        message_start = {'type': 'message_start', 'message': {'id': 'msg', 'role': 'assistant', 'content': []}}
        message_tool = {'type': 'content_block_start', 'index': 0, 'content_block':
                        {'type': 'tool_use', 'id': 'tool-msg', 'name': TOOL['name'], 'input': {}}}
        message_delta = {'type': 'content_block_delta', 'index': 0,
                         'delta': {'type': 'input_json_delta', 'partial_json': DELTA['delta']}}
        message_done = [message_start, {'type': 'content_block_start', 'index': 0,
            'content_block': {'type': 'text', 'text': 'OK'}}, {'type': 'content_block_stop', 'index': 0},
            {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}}, {'type': 'message_stop'}]
        cases = [('chat-completions', [chat_delta], [chat_done, '[DONE]']),
                 ('messages', [message_start, message_tool, message_delta], message_done)]
        for protocol, partial, complete in cases:
            with self.subTest(protocol=protocol):
                await self.serve([http_stream(partial, interrupted=True), http_stream(complete)], protocol=protocol)
                result = await self.infer()
                self.assertEqual(result['content'][0], {'type': 'text', 'text': 'OK'})
                self.assertEqual(self.received[-2], self.received[-1])
        self.assertEqual(self.timers, [60, 60])

    async def test_visible_text_completed_arguments_unknown_item_and_truncated_event_hold(self):
        shown = {'type': 'response.output_text.delta', 'output_index': 0, 'delta': 'Already visible'}
        done = {**DELTA, 'type': 'response.function_call_arguments.done'}
        foreign = {**ITEM, 'item': {**ITEM['item'], 'name': 'undocumented-tool'}}
        streams = [http_stream([START, shown, ITEM, DELTA], interrupted=True),
                   http_stream([*PARTIAL, done], interrupted=True),
                   http_stream([START, foreign, DELTA], interrupted=True),
                   http_stream(PARTIAL, interrupted=True, tail=b'data: {"type":"response.')]
        await self.serve(streams)
        for _ in streams:
            with self.assertRaises(ModelFault) as caught:
                await self.infer()
            self.assertFalse(caught.exception.partial_tool_stream)
        self.assertEqual(len(self.received), len(streams))
        self.assertEqual(self.timers, [])
        self.assertEqual(self.text, ['Already visible'])

    async def test_preserves_old_run_retry_policy(self):
        self.config['streamRetryProtocol'] = 2
        await self.serve([http_stream(PARTIAL, interrupted=True)])
        with self.assertRaises(ModelFault) as caught:
            await self.infer()
        self.assertFalse(caught.exception.partial_tool_stream)
        self.assertEqual(self.timers, [])

    async def test_unconfirmed_previous_tool_prevents_retry(self):
        self.previous_receipt({'success': False, 'error': 'unknown'})
        await self.serve([http_stream(PARTIAL, interrupted=True)])
        with self.assertRaises(ModelFault) as caught:
            await self.infer()
        self.assertTrue(caught.exception.partial_tool_stream)
        self.assertEqual(self.timers, [])
        self.assertEqual(len(self.received), 1)

    async def test_receipt_changed_before_dispatch_prevents_second_request(self):
        self.previous_receipt({'success': True, 'output': 'Original result'})
        await self.serve([http_stream(PARTIAL, interrupted=True)])

        async def boundary(*, allow_play):
            with self.store.db:
                self.store.db.execute("UPDATE tools SET state='unknown' WHERE call_id='previous-result'")

        self.goal.boundary.side_effect = boundary
        with self.assertRaises(ModelFault) as caught:
            await self.infer()
        self.assertEqual(caught.exception.code, 'model_tool_stream_retry_unavailable')
        self.assertEqual(self.timers, [60])
        self.assertEqual(self.retry()['state'], 'cancelled')
        self.assertEqual(len(self.received), 1)


if __name__ == '__main__':
    unittest.main()
