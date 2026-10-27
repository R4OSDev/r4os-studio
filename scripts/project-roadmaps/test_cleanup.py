"""Real files, SQLite journal and interruption recovery; no user data or inference."""
import hashlib
import json
import unittest
from unittest.mock import patch
import uuid

from cli import operation
import cleanup
from storage import connection, RoadmapFault
import test_storage


class CleanupTests(unittest.TestCase):
    def setUp(self):
        test_storage.RoadmapStorageTests.setUp(self)
        self.project_id = self.ids[0]
        self.source = self.root / self.project_id / 'Workspace'
        self.actor = {'config': {'permissions': {'studio.' + t: True for t in ('read_file', 'write_file', 'create_directory')}},
                      'sessionId': str(uuid.uuid4()), 'contexts': [{'runId': str(uuid.uuid4()), 'text': 'Bitte Roadmap aufräumen.'}], 'check': lambda: None}
        self.request('initialize', requestId=str(uuid.uuid4()))

    def request(self, name, **extra):
        return operation(self.root, {'operation': name, 'projectId': self.project_id, **extra})

    def change(self, action, target, content):
        bound = self.request('revision')
        return self.request('mutate', input={'requestId': str(uuid.uuid4()), 'expectedRevision': bound['revision'],
                                            'currentVersionId': bound['currentVersionId'], 'target': target, 'action': action, 'input': content})

    def arguments(self):
        bound = self.request('revision')
        return {'action': 'prepare', 'requestId': str(uuid.uuid4()), 'versionId': bound['currentVersionId'],
                'currentVersionId': bound['currentVersionId'], 'expectedRevision': bound['revision'], 'cleanupRequested': True}

    def call(self, arguments):
        with connection(self.root, self.project_id) as db:
            return cleanup.call(db, self.root, self.project_id, arguments, self.actor)

    def fixture(self):
        roadmap = self.request('overview')['roadmap']; version_id = roadmap['currentVersionId']
        self.change('update', {'kind': 'roadmap', 'id': roadmap['id']}, {'notes': 'Shared project notes ä🙂\nSecond line'})
        self.change('update', {'kind': 'version', 'id': version_id}, {'vision': 'Durable architecture', 'notes': 'Version notes'})
        sub = self.change('create', {'kind': 'subversion', 'versionId': version_id}, {'title': 'Finished work', 'status': 'complete', 'notes': 'Sub notes'})['entity']
        for kind in ('task', 'acceptance'):
            self.change('create', {'kind': kind, 'versionId': version_id, 'subversionId': sub['id']},
                        {'description': kind + ' done', 'status': 'done', 'notes': 'Actual evidence ' + kind})
        discarded = self.change('create', {'kind': 'subversion', 'versionId': version_id},
                                {'title': 'Discarded work', 'status': 'discarded', 'notes': 'Not needed for the chosen role'})['entity']
        self.change('create', {'kind': 'task', 'versionId': version_id, 'subversionId': discarded['id']},
                    {'description': 'Historical open child of discarded work', 'notes': 'Preserve historical status'})
        return version_id

    def test_complete_archive_and_document_checkpoint_preserve_all_domain_state(self):
        self.fixture()
        docs = self.source / 'Docs'; docs.mkdir()
        old = docs / 'Architecture.md'; old.write_text('Existing user knowledge\n')
        before_hash = hashlib.sha256(old.read_bytes()).hexdigest()
        before = self.request('read')
        args = self.arguments(); prepared = self.call(args)
        path = self.source / prepared['archive']['path']; raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), prepared['archive']['sha256'])
        self.assertTrue(raw.endswith(b'# End of complete version archive\n'))
        for phrase in ['Shared project notes ä🙂', 'Durable architecture', 'Version notes', 'Sub notes', 'Actual evidence task',
                       'Actual evidence acceptance', 'Historical open child of discarded work', 'Not needed for the chosen role']:
            self.assertIn(phrase, raw.decode())
        self.assertEqual(path.name, '0.1.X.txt')
        self.assertEqual(self.request('read'), before)
        old.write_text('Existing user knowledge\nDurable architecture from roadmap\n')
        selected = {'path': 'Docs/Architecture.md', 'expectedSha256': before_hash, 'sha256': hashlib.sha256(old.read_bytes()).hexdigest()}
        checkpoint = {**args, 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'],
                      'documents': [selected], 'documentationSummary': 'Preserved existing knowledge and extracted the architecture decision.'}
        confirmed = self.call(checkpoint)
        self.assertEqual(confirmed['phase'], 'documents_verified'); self.assertEqual(confirmed['documents'], [{**selected, 'byteLength': len(old.read_bytes())}])
        self.assertEqual(self.call(args), prepared)  # Exact original receipt, without a repeated filesystem action.
        self.assertEqual(self.call(checkpoint), confirmed)
        status = self.call({'action': 'status', 'workflowId': prepared['workflowId'], 'documents': [{**selected, 'expectedSha256': None}]})
        self.assertEqual(status['documentStatus'][0]['baselineSha256'], before_hash)
        self.assertTrue(status['documentStatus'][0]['reportedHashMatchesReceipt'])
        self.assertEqual(self.request('read'), before)
        with self.assertRaises(RoadmapFault): self.change('update', {'kind': 'version', 'id': args['versionId']}, {'title': 'Blocked during cleanup'})
        unavailable = self.call({'action': 'finalize'})
        self.assertFalse(unavailable['available']); self.assertEqual(self.request('read'), before)

    def test_crash_after_archive_publication_resumes_original_workflow_without_rewrite(self):
        args = self.arguments()
        with patch('cleanup.receipt', side_effect=OSError('Own simulated lost journal response')):
            with self.assertRaises(OSError): self.call(args)
        archive = self.source / 'Docs/Changelogs/0.1.X.txt'
        raw, inode = archive.read_bytes(), archive.stat().st_ino
        status = self.call({'action': 'status', 'workflowId': args['requestId']})
        self.assertEqual(status['phase'], 'archiving')
        confirmed = self.call(args)
        self.assertEqual(confirmed['phase'], 'archive_ready')
        self.assertEqual(archive.read_bytes(), raw); self.assertEqual(archive.stat().st_ino, inode)
        self.assertEqual(len(self.request('read')['roadmap']['versions']), 1)

    def test_partial_own_stage_is_preserved_and_next_attempt_publishes_only_one_archive(self):
        args = self.arguments()
        partial = []
        def interrupted(root_fd, stream, info, temporary, check):
            directory = self.source / 'Docs/Changelogs'; directory.mkdir(parents=True)
            path = directory / temporary; path.write_bytes(b'own interrupted stage'); partial.append(path)
            raise OSError('Own interrupted copy')
        with patch('cleanup.archive', side_effect=interrupted), self.assertRaises(OSError): self.call(args)
        recovered = self.call(args)
        self.assertEqual(recovered['attemptCount'], 2)
        self.assertEqual(partial[0].read_bytes(), b'own interrupted stage')
        self.assertEqual(len(list((self.source / 'Docs/Changelogs').glob('*.txt'))), 1)
        self.assertTrue((self.source / recovered['archive']['path']).read_bytes().endswith(b'# End of complete version archive\n'))

    def test_rights_explicit_context_current_binding_and_open_work_are_required(self):
        args = self.arguments(); before = self.request('read')
        for tool in ('read_file', 'write_file', 'create_directory'):
            self.actor['config']['permissions']['studio.' + tool] = False
            with self.assertRaises(RoadmapFault): self.call(args)
            self.actor['config']['permissions']['studio.' + tool] = True
        self.actor['contexts'][0]['text'] = 'Roadmap abarbeiten.'
        with self.assertRaises(RoadmapFault): self.call(args)
        self.actor['contexts'][0]['text'] = 'Please tidy up the roadmap.'
        with self.assertRaises(RoadmapFault): self.call({**args, 'currentVersionId': str(uuid.uuid4())})
        self.assertFalse((self.source / 'Docs').exists()); self.assertEqual(self.request('read'), before)
        sub = self.change('create', {'kind': 'subversion', 'versionId': args['versionId']}, {'title': 'Still open'})['entity']
        with self.assertRaises(RoadmapFault): self.call(self.arguments())
        self.change('update', {'kind': 'subversion', 'versionId': args['versionId'], 'id': sub['id']}, {'status': 'complete'})
        task = self.change('create', {'kind': 'acceptance', 'versionId': args['versionId'], 'subversionId': sub['id']}, {'description': 'Not tested'})['entity']
        with self.assertRaises(RoadmapFault): self.call(self.arguments())
        with connection(self.root, self.project_id) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM workflows').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT status FROM acceptances WHERE id=?', (task['id'],)).fetchone()[0], 'open')

    def test_conflicting_archive_and_links_are_preserved_and_cancel_does_not_undo_files(self):
        directory = self.source / 'Docs/Changelogs'; directory.mkdir(parents=True)
        path = directory / '0.1.X.txt'; path.write_text('User archive must remain exact')
        args = self.arguments()
        with self.assertRaises(RoadmapFault): self.call(args)
        self.assertEqual(path.read_text(), 'User archive must remain exact')
        cancelled = self.call({'action': 'cancel', 'workflowId': args['requestId'], 'requestId': str(uuid.uuid4())})
        self.assertEqual(cancelled['phase'], 'cancelled'); self.assertTrue(path.exists())
        # Reconcile the same cancelled version with the still-authorized original
        # context; this does not require another blanket user confirmation.
        path.unlink(); resumed_args = self.arguments(); resumed = self.call(resumed_args)
        self.assertEqual(resumed['phase'], 'archive_ready')
        self.call({'action': 'cancel', 'workflowId': resumed_args['requestId'], 'requestId': str(uuid.uuid4())})
        path.unlink(); outside = self.source.parent / 'outside.txt'; outside.write_text('Keep outside file')
        path.symlink_to(outside)
        self.actor['contexts'].insert(0, {'runId': str(uuid.uuid4()), 'text': 'Clean up the roadmap.'})
        with self.assertRaises(RoadmapFault): self.call(self.arguments())
        self.assertTrue(path.is_symlink()); self.assertEqual(outside.read_text(), 'Keep outside file')

    def test_document_paths_original_final_hashes_and_workspace_replacement_are_checked(self):
        docs = self.source / 'Docs'; docs.mkdir(); file = docs / 'Decision.md'; file.write_text('Original decision')
        old_hash = hashlib.sha256(file.read_bytes()).hexdigest()
        args = self.arguments(); prepared = self.call(args); file.write_text('Original decision\nNew knowledge')
        checkpoint = {**args, 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'],
                      'documentationSummary': 'Extracted the durable decision.',
                      'documents': [{'path': 'Docs/Decision.md', 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'expectedSha256': old_hash}]}
        for invalid in ({'path': 'Docs/../outside.txt'}, {'expectedSha256': None}, {'sha256': 'f' * 64}, {'path': 'Docs/Changelogs/0.1.X.txt'}):
            bad = {**checkpoint, 'requestId': str(uuid.uuid4()), 'documents': [{**checkpoint['documents'][0], **invalid}]}
            with self.assertRaises(RoadmapFault): self.call(bad)
        self.assertEqual(file.read_text(), 'Original decision\nNew knowledge')
        saved = self.source.with_name('SavedWorkspace'); self.source.rename(saved); self.source.mkdir()
        (self.source / 'module.R4MF').write_text('Own replacement fixture')
        with self.assertRaises(RoadmapFault): self.call(checkpoint)
        self.assertFalse((self.source / 'Docs').exists()); self.assertTrue((saved / 'Docs/Changelogs/0.1.X.txt').exists())

    def test_document_checkpoint_never_recreates_a_missing_confirmed_archive(self):
        args = self.arguments(); prepared = self.call(args)
        path = self.source / prepared['archive']['path']; path.unlink()
        checkpoint = {**args, 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'], 'documents': [],
                      'documentationSummary': 'The empty version contains no additional durable knowledge.'}
        with self.assertRaises(RoadmapFault): self.call(checkpoint)
        self.assertFalse(path.exists())
        self.assertEqual(self.call({'action': 'status', 'workflowId': prepared['workflowId']})['phase'], 'archive_ready')
