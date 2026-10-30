"""Completed response input/cache accounting, replay and lifetime retention."""
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from claude_input_usage import InputUsage, record
from claude_runtime import profile
from stats_store import Source, read, scope
from stats_lifecycle import preserve_pending, flush_pending
from store import ProjectFault
import test_runs as fixtures


class ClaudeInputUsage(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def worker(self, store):
        p = profile(); native = str(uuid.uuid4())
        return SimpleNamespace(store=store, session_id=self.sid, run_id=str(uuid.uuid4()),
            config={'providerId': self.provider, 'engine': {'kind': 'claude-code', 'claude': {
                'nativeSessionId': native, 'studioSessionId': self.sid, 'providerId': self.provider,
                'runtimeProfileId': p['id'], 'sha256': p['native']['files']['claude']['sha256'],
                'sdkArchiveSha256': p['sdk']['archiveSha256']}}})

    def message(self, worker, ident='msg_owned_one'):
        return {'type': 'assistant', 'session_id': worker.config['engine']['claude']['nativeSessionId'],
            'uuid': str(uuid.uuid4()), 'parent_tool_use_id': None, 'message': {'id': ident,
                'content': [{'type': 'text', 'text': 'Owned response text must not enter accounting'}],
                'usage': {'input_tokens': 12, 'cache_creation_input_tokens': 30,
                    'cache_read_input_tokens': 50, 'output_tokens': 999999}}}

    def test_parallel_blocks_and_resumed_replay_count_once_with_unknown_output(self):
        with self.open() as store:
            w = self.worker(store); m = self.message(w)
            first = record(w, m, m['message']['usage'])
            duplicate = {**m, 'uuid': str(uuid.uuid4())}
            self.assertEqual(record(w, duplicate, m['message']['usage']), first)
            w.run_id = str(uuid.uuid4())
            self.assertEqual(record(w, duplicate, m['message']['usage']), first)
            Source(store).flush(include_acknowledged=True)
            self.assertEqual(store.db.execute('SELECT count(*) FROM claude_input_usage').fetchone()[0], 1)
            audit = store.db.execute('SELECT payload FROM claude_input_usage').fetchone()[0]
            self.assertNotIn('Owned response text', audit); self.assertNotIn('999999', audit)
        totals = read(self.projects)['tokens']
        self.assertEqual((totals['input'], totals['cacheWrite'], totals['cachedInput']), ('92', '30', '50'))
        self.assertIsNone(totals['output']); self.assertIsNone(totals['total']); self.assertIsNone(totals['reasoningOutput'])

    def test_completion_boundary_is_required_and_unfinished_stream_is_a_gap(self):
        with self.open() as store:
            w = self.worker(store); message = self.message(w); usage = InputUsage(w)
            usage.notify({'type': 'stream_event', 'event': {'type': 'message_start', 'message': {'id': message['message']['id']}}})
            usage.notify(message)
            self.assertFalse(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='claude_input_usage'").fetchone())
            usage.notify({'type': 'stream_event', 'event': {'type': 'message_stop'}})
            usage.notify({**message, 'uuid': str(uuid.uuid4())})
            usage.finish()
            self.assertEqual(read(self.projects)['tokens']['input'], '92')
            second = self.message(w, 'msg_owned_unfinished')
            incomplete = InputUsage(w); incomplete.notify(second); incomplete.finish()
            self.assertEqual(read(self.projects)['tokens']['input'], '92')
            self.assertTrue(read(self.projects)['coverage']['hasGaps'])
            # A per-block message cannot cause this tracker to retain response
            # text or large tool/image payloads in its pending accounting map.
            self.assertNotIn('Owned response text', json.dumps(usage.pending))

    def test_conflicts_foreign_scope_and_invalid_values_preserve_original(self):
        with self.open() as store:
            w = self.worker(store); message = self.message(w)
            original = record(w, message, message['message']['usage'])
            for value in (True, -1, 2**53, 1.5):
                with self.assertRaises(ProjectFault): record(w, message, {'input_tokens': value})
            for change in ({'session_id': str(uuid.uuid4())}, {'parent_tool_use_id': 'toolu_foreign'}, {'error': 'overloaded'}):
                with self.assertRaises(ProjectFault): record(w, message | change, message['message']['usage'])
            changed = message['message']['usage'] | {'input_tokens': 13}
            with self.assertRaises(ProjectFault): record(w, message, changed)
            self.assertEqual(record(w, message, message['message']['usage']), original)
            bad = copy.deepcopy(w.config); bad['engine']['claude']['studioSessionId'] = str(uuid.uuid4())
            with patch.object(w, 'config', bad), self.assertRaises(ProjectFault): record(w, message, message['message']['usage'])
            Source(store).flush(); self.assertEqual(read(self.projects)['tokens']['input'], '92')

    def test_missing_cache_is_unknown_reported_zero_and_numeric_retention(self):
        with self.open() as store:
            w = self.worker(store); message = self.message(w)
            first = record(w, message, {'input_tokens': 12, 'cache_read_input_tokens': 0})
            self.assertNotIn('input', first['values']); self.assertNotIn('cacheWrite', first['values'])
            record(w, self.message(w, 'msg_owned_zero'), {field: 0 for field in
                ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')})
            # A blocked global store must not discard the numeric outbox when
            # deleting the selected session and its private native audit data.
            with patch('stats_lifecycle.Source.flush', side_effect=ProjectFault('Owned unavailable global store', 503)):
                self.assertEqual(preserve_pending(self.projects, store.directory/'Sessions.sqlite'), 2)
            pending = list((self.projects/'.studio/statistics/Pending').glob('*.json'))
            for path in pending:
                raw = path.read_text(); self.assertNotIn(w.config['engine']['claude']['nativeSessionId'], raw)
                self.assertNotIn('msg_owned', raw); self.assertNotIn(self.sid, raw)
            with store.db:
                store.db.execute('DELETE FROM claude_input_usage WHERE session_id=?', (self.sid,))
                store.db.execute('DELETE FROM statistic_receipts')
                store.db.execute('DELETE FROM sessions WHERE id=?', (self.sid,))
        self.assertEqual(flush_pending(self.projects), 2)
        global_totals = read(self.projects)['tokens']
        self.assertEqual(global_totals['input'], '0'); self.assertEqual(global_totals['cachedInput'], '0')
        self.assertIsNone(global_totals['total']); self.assertEqual(global_totals['cacheWrite'], '0')
        self.assertEqual(read(self.projects, 'session:'+scope({'type':'project','id':self.pid}, self.sid))['tokens'], global_totals)
