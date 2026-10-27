"""Finalization gates, all-or-nothing SQLite commit and exact original replay."""
import hashlib
import unittest
from unittest.mock import patch
import uuid

import test_cleanup
from storage import connection, RoadmapFault


class FinalizeTests(unittest.TestCase):
    request = test_cleanup.CleanupTests.request
    change = test_cleanup.CleanupTests.change
    arguments = test_cleanup.CleanupTests.arguments
    call = test_cleanup.CleanupTests.call
    fixture = test_cleanup.CleanupTests.fixture

    def setUp(self):
        test_cleanup.CleanupTests.setUp(self)
        self.actor['verify_origin'] = lambda origin: next((entry['text'] for entry in self.actor['contexts'] if entry['runId'] == origin['runId']), None)

    def ready(self, with_document=False):
        args = self.arguments(); prepared = self.call(args)
        documents = []
        if with_document:
            path = self.source / 'Docs/Knowledge.md'; path.write_text('Durable knowledge from the complete roadmap\n')
            documents = [{'path': 'Docs/Knowledge.md', 'expectedSha256': None, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}]
        summary = 'Reviewed the full roadmap; knowledge is in the selected document.' if documents else 'Reviewed the empty version; no durable knowledge requires a separate document beyond the complete archive.'
        verified = self.call({**args, 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'],
                              'documents': documents, 'documentationSummary': summary})
        final = {'action': 'finalize', 'requestId': str(uuid.uuid4()), 'workflowId': verified['workflowId'],
                 'cleanupRequested': True, 'documents': documents, 'documentationSummary': summary}
        return prepared, final

    def test_complete_next_empty_current_are_atomic_and_history_notes_stay_exact(self):
        old_id = self.fixture(); before = self.request('read')['roadmap']
        prepared, final = self.ready(with_document=True)
        archive = self.source / prepared['archive']['path']; raw = archive.read_bytes()
        result = self.call(final)
        self.assertEqual(result['phase'], 'complete'); self.assertEqual(result['nextNumber'], '0.2.X')
        after = self.request('read')['roadmap']
        self.assertEqual(after['notes'], before['notes']); self.assertEqual(after['description'], before['description']); self.assertEqual(after['id'], before['id'])
        previous = next(v for v in after['versions'] if v['id'] == old_id)
        original = next(v for v in before['versions'] if v['id'] == old_id)
        self.assertEqual(previous['status'], 'complete')
        for field in ('title', 'vision', 'notes', 'subversions', 'number', 'order', 'createdAt'): self.assertEqual(previous[field], original[field])
        following = next(v for v in after['versions'] if v['id'] == after['currentVersionId'])
        self.assertEqual(following['id'], result['nextVersionId']); self.assertEqual(following['number'], '0.2.X')
        self.assertEqual((following['title'], following['status'], following['vision'], following['notes'], following['subversions']), ('New', 'open', '', '', []))
        self.assertEqual(len(after['versions']), 2); self.assertEqual(archive.read_bytes(), raw)
        self.assertEqual(self.call(final), result)
        self.assertEqual(self.call({**final, 'requestId': str(uuid.uuid4())}), result)
        self.assertEqual(self.request('read')['roadmap'], after)

    def test_failure_before_db_commit_rolls_back_complete_next_and_current_together(self):
        prepared, final = self.ready(); before = self.request('read')
        archive = self.source / prepared['archive']['path']; raw = archive.read_bytes()
        with patch('cleanup.receipt', side_effect=OSError('Own injected receipt failure before commit')):
            with self.assertRaises(OSError): self.call(final)
        self.assertEqual(self.request('read'), before)
        self.assertEqual(self.call({'action': 'status', 'workflowId': prepared['workflowId']})['phase'], 'documents_verified')
        self.assertEqual(archive.read_bytes(), raw)
        result = self.call(final); self.assertEqual(result['phase'], 'complete')
        self.assertEqual(len(self.request('read')['roadmap']['versions']), 2)

    def test_changed_documents_archive_context_and_read_permission_block_finalization(self):
        prepared, final = self.ready(with_document=True); before = self.request('read')
        knowledge = self.source / 'Docs/Knowledge.md'; source_text = knowledge.read_text()
        knowledge.write_text('Concurrent user change must survive')
        with self.assertRaises(RoadmapFault): self.call(final)
        self.assertEqual(knowledge.read_text(), 'Concurrent user change must survive'); knowledge.write_text(source_text)
        archive = self.source / prepared['archive']['path']; raw = archive.read_bytes(); archive.write_bytes(raw + b'changed')
        with self.assertRaises(RoadmapFault): self.call(final)
        self.assertEqual(archive.read_bytes(), raw + b'changed'); archive.write_bytes(raw)
        self.actor['verify_origin'] = lambda _: 'Only work through the roadmap.'
        with self.assertRaises(RoadmapFault): self.call(final)
        self.actor['verify_origin'] = lambda _: self.actor['contexts'][0]['text']
        self.actor['config']['permissions']['studio.read_file'] = False
        with self.assertRaises(RoadmapFault): self.call(final)
        self.assertEqual(self.request('read'), before)

    def test_existing_next_version_is_a_conflict_and_keeps_its_content(self):
        future = self.change('create', {'kind': 'version'}, {'number': '0.2.X', 'title': 'Existing future', 'vision': 'Do not replace', 'notes': 'Future notes'})['entity']
        _, final = self.ready(); before = self.request('read')
        with self.assertRaisesRegex(RoadmapFault, 'already exists'): self.call(final)
        self.assertEqual(self.request('read'), before)
        self.assertEqual(self.request('get', target={'kind': 'version', 'id': future['id']})['entity']['vision'], 'Do not replace')

    def test_missing_checkpoint_wrong_selection_cancel_and_stale_revision_are_not_success(self):
        args = self.arguments(); prepared = self.call(args)
        final = {'action': 'finalize', 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'], 'cleanupRequested': True,
                 'documents': [], 'documentationSummary': 'Not verified'}
        with self.assertRaises(RoadmapFault): self.call(final)
        _, payload = self.ready_for_existing(args, prepared)
        for invalid in ({'cleanupRequested': False}, {'documentationSummary': 'Different summary'}, {'workflowId': str(uuid.uuid4())}):
            with self.assertRaises(RoadmapFault): self.call({**payload, **invalid, 'requestId': str(uuid.uuid4())})
        before = self.request('read')
        with connection(self.root, self.project_id) as db, db: db.execute('UPDATE roadmap SET revision=revision+1')
        with self.assertRaises(RoadmapFault): self.call(payload)
        self.assertEqual(len(self.request('read')['roadmap']['versions']), 1)
        self.call({'action': 'cancel', 'workflowId': prepared['workflowId'], 'requestId': str(uuid.uuid4())})
        with self.assertRaises(RoadmapFault): self.call(payload)
        self.assertEqual(self.request('read')['roadmap']['versions'], before['roadmap']['versions'])

    def ready_for_existing(self, args, prepared):
        summary = 'No durable knowledge beyond the complete empty-version archive.'
        verified = self.call({**args, 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'], 'documents': [], 'documentationSummary': summary})
        return verified, {'action': 'finalize', 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'], 'cleanupRequested': True, 'documents': [], 'documentationSummary': summary}

    def test_version_increment_is_numeric_and_overflow_preserves_original(self):
        current = self.request('current')['entity']
        self.change('update', {'kind': 'version', 'id': current['id']}, {'number': '0.9.X'})
        _, final = self.ready(); self.assertEqual(self.call(final)['nextNumber'], '0.10.X')
        current = self.request('current')['entity']
        self.change('update', {'kind': 'version', 'id': current['id']}, {'number': '0.2147483647.X'})
        self.actor['contexts'].insert(0, {'runId': str(uuid.uuid4()), 'text': 'Please clean up the roadmap.'})
        _, final = self.ready(); before = self.request('read')
        with self.assertRaises(RoadmapFault): self.call(final)
        self.assertEqual(self.request('read'), before)
