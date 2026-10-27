import hashlib
import os
from pathlib import Path
import unittest
import uuid
import test_storage
from cli import operation
import exports
from storage import RoadmapFault


class RoadmapExportTests(unittest.TestCase):
    setUp = test_storage.RoadmapStorageTests.setUp

    def request(self, name, project_id=None, **extra):
        return operation(self.root, {'operation': name, 'projectId': project_id or self.ids[0], **extra})

    def initialize(self, project_id=None):
        self.request('initialize', project_id, requestId=str(uuid.uuid4()))
        return self.request('overview', project_id)['roadmap']

    def change(self, action, target, data):
        root = self.request('overview')['roadmap']
        return self.request('mutate', input={'requestId': str(uuid.uuid4()), 'expectedRevision': root['revision'],
                                            'currentVersionId': root['currentVersionId'], 'action': action, 'target': target, 'input': data})

    def export_input(self, version_id, project_id=None):
        root = self.request('overview', project_id)['roadmap']
        return {'requestId': str(uuid.uuid4()), 'versionId': version_id, 'expectedRevision': root['revision'], 'currentVersionId': root['currentVersionId']}

    def fixture(self):
        root = self.initialize(); version_id = root['currentVersionId']
        self.change('update', {'kind': 'roadmap', 'id': root['id']}, {'description': 'Shared description', 'notes': 'Project notes ä🙂\r\nSecond project line'})
        self.change('update', {'kind': 'version', 'id': version_id}, {'title': 'Historic title', 'vision': 'A durable vision', 'notes': 'Version notes\nSecond line', 'status': 'complete'})
        sub = self.change('create', {'kind': 'subversion', 'versionId': version_id},
                          {'title': 'Discarded subversion', 'description': 'Sub description', 'notes': 'Sub notes', 'status': 'discarded'})['entity']
        items = []
        for index, status in enumerate(('open', 'done', 'discarded')):
            items.append(self.change('create', {'kind': 'task', 'versionId': version_id, 'subversionId': sub['id']},
                                     {'description': f'Task {index}', 'notes': f'Task notes {index} é🙂\n' + 'n' * (17000 if index == 0 else 0), 'status': status})['entity'])
        acceptance = self.change('create', {'kind': 'acceptance', 'versionId': version_id, 'subversionId': sub['id']},
                                 {'description': 'Acceptance description', 'notes': 'Acceptance notes must survive\nEven when discarded', 'status': 'discarded'})['entity']
        next_version = self.change('create', {'kind': 'version'}, {'title': 'Next', 'number': '0.2.X'})['entity']
        self.change('set_current', {'kind': 'version', 'id': next_version['id']}, {})
        return version_id, sub, items, acceptance

    def test_complete_deterministic_historical_snapshot_preserves_all_notes_and_status(self):
        version_id, sub, tasks, acceptance = self.fixture()
        before = self.request('read')['roadmap']
        body = self.export_input(version_id)
        info = self.request('export', input=body)
        file = self.root / self.ids[0] / 'Roadmap/Exports' / info['id'] / 'archive.txt'
        raw = file.read_bytes(); text = raw.decode('utf-8')
        self.assertEqual(info['filename'], '0.1.X.txt')
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(info['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(info['byteLength'], len(raw))
        for value in [before['id'], before['projectId'], version_id, sub['id'], acceptance['id'], *[x['id'] for x in tasks],
                      before['notes'], 'Shared description', 'A durable vision', 'Version notes\nSecond line', sub['notes'], sub['description'],
                      acceptance['description'], acceptance['notes'], *[x['notes'] for x in tasks], *[x['description'] for x in tasks]]:
            self.assertIn(value, text)
        for status in ('Open', 'Done', 'Discarded', 'Complete'):
            self.assertIn('Status: ' + status, text)
        self.assertIn('Created: ' + sub['createdAt'], text)
        self.assertIn('Order: 0', text)
        self.assertTrue(text.endswith('# End of complete version archive\n'))
        self.assertEqual(self.request('read')['roadmap'], before)
        again = self.request('export', input=self.export_input(version_id))
        self.assertEqual(again['sha256'], info['sha256'])
        self.assertEqual(self.request('export', input=body), info)

    def test_snapshot_is_immutable_after_later_edits_and_chunks_are_utf8_safe(self):
        version_id, sub, _, _ = self.fixture()
        body = self.export_input(version_id); info = self.request('export', input=body)
        self.change('append_notes', {'kind': 'subversion', 'versionId': version_id, 'id': sub['id']}, {'notes': 'After snapshot'})
        self.assertEqual(self.request('export', input=body), info)
        text, offset = '', 0
        while True:
            page = self.request('export_chunk', exportId=info['id'], offset=offset, limit=997)
            self.assertEqual(page['offset'], offset)
            text += page['text']
            if page['nextOffset'] is None:
                break
            self.assertGreater(page['nextOffset'], offset); offset = page['nextOffset']
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), info['sha256'])
        self.assertNotIn('After snapshot', text)
        position = text.encode().index('🙂'.encode()) + 1
        with self.assertRaises(RoadmapFault) as error:
            self.request('export_chunk', exportId=info['id'], offset=position)
        self.assertEqual(error.exception.code, 400)

    def test_foreign_ids_request_reuse_and_stale_bindings_are_rejected(self):
        root = self.initialize(); foreign = self.initialize(self.ids[1])
        body = self.export_input(root['currentVersionId']); result = self.request('export', input=body)
        with self.assertRaises(RoadmapFault) as error:
            self.request('export', input={**body, 'versionId': foreign['currentVersionId']})
        self.assertEqual(error.exception.code, 409)
        with self.assertRaises(RoadmapFault) as error:
            self.request('export', input={**self.export_input(root['currentVersionId']), 'versionId': foreign['currentVersionId']})
        self.assertEqual(error.exception.code, 404)
        with self.assertRaises(RoadmapFault) as error:
            self.request('export_info', self.ids[1], exportId=result['id'])
        self.assertEqual(error.exception.code, 410)
        stale = self.export_input(root['currentVersionId'])
        self.change('append_notes', {'kind': 'roadmap', 'id': root['id']}, {'notes': 'New'})
        with self.assertRaises(RoadmapFault) as error:
            self.request('export', input=stale)
        self.assertEqual(error.exception.code, 409)

    def test_corrupt_archive_is_preserved_and_limits_never_publish_partial_output(self):
        root = self.initialize(); info = self.request('export', input=self.export_input(root['currentVersionId']))
        path = self.root / self.ids[0] / 'Roadmap/Exports' / info['id'] / 'archive.txt'
        os.chmod(path, 0o600); corrupted = b'!' + path.read_bytes()[1:]; path.write_bytes(corrupted)
        with self.assertRaises(RoadmapFault) as error:
            self.request('export_info', exportId=info['id'])
        self.assertEqual(error.exception.code, 503)
        self.assertEqual(path.read_bytes(), corrupted)
        foreign = self.initialize(self.ids[1]); body = self.export_input(foreign['currentVersionId'], self.ids[1])
        original = exports.MAX_ARCHIVE_BYTES; exports.MAX_ARCHIVE_BYTES = 8
        try:
            with self.assertRaises(RoadmapFault) as error:
                self.request('export', self.ids[1], input=body)
            self.assertEqual(error.exception.code, 413)
        finally:
            exports.MAX_ARCHIVE_BYTES = original
        self.assertFalse((self.root / self.ids[1] / 'Roadmap/Exports' / body['requestId']).exists())
        self.assertEqual(self.request('overview', self.ids[1])['roadmap'], foreign)


if __name__ == '__main__':
    unittest.main()
