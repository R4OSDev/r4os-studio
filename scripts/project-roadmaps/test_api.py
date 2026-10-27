from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid
import test_storage
from cli import operation
from storage import RoadmapFault


class RoadmapApiTests(unittest.TestCase):
    setUp = test_storage.RoadmapStorageTests.setUp

    def request(self, name, project_id=None, **extra):
        return operation(self.root, {'operation': name, 'projectId': project_id or self.ids[0], **extra})

    def initialize(self, project_id=None):
        self.request('initialize', project_id, requestId=str(uuid.uuid4()))
        return self.request('overview', project_id)['roadmap']

    def body(self, action, reference, data=None, binding=None):
        state = binding or self.request('overview')['roadmap']
        return {'requestId': str(uuid.uuid4()), 'expectedRevision': state['revision'],
                'currentVersionId': state['currentVersionId'], 'action': action,
                'target': reference, 'input': data or {}}

    def change(self, action, reference, data=None):
        return self.request('mutate', input=self.body(action, reference, data))

    def test_crud_all_hierarchy_levels_notes_status_and_order(self):
        root = self.initialize(); version_id = root['currentVersionId']
        self.change('update', {'kind': 'roadmap', 'id': root['id']}, {'description': 'Shared roadmap', 'notes': 'Root notes'})
        self.change('update', {'kind': 'version', 'id': version_id}, {'title': 'Milestone', 'vision': 'A usable app', 'notes': 'Version notes'})
        sub = self.change('create', {'kind': 'subversion', 'versionId': version_id}, {'title': 'First', 'number': '0.1.1', 'notes': 'Sub notes'})['entity']
        reference = {'kind': 'subversion', 'versionId': version_id, 'id': sub['id']}
        self.change('update', reference, {'description': ''})
        items = []
        for kind in ('task', 'acceptance'):
            parent = {'kind': kind, 'versionId': version_id, 'subversionId': sub['id']}
            created = self.change('create', parent, {'description': kind, 'notes': 'Initial'})['entity']
            ref = {**parent, 'id': created['id']}; items.append(ref)
            self.change('append_notes', ref, {'notes': 'More'})
            self.assertEqual(self.request('notes', target=ref)['notes'], 'Initial\nMore')
            self.change('replace_notes', ref, {'notes': 'Final notes'})
            self.change('update', ref, {'status': 'done'})
        got = self.request('get', target=reference)['entity']
        self.assertEqual(got['status'], 'open')
        self.assertEqual(got['progress']['tasks']['done'], 1)
        self.assertEqual(got['progress']['acceptances']['done'], 1)
        self.change('update', reference, {'number': '0.1.7', 'status': 'complete'})
        self.assertEqual(self.request('get', target=reference)['entity']['number'], '0.1.7')
        another = self.change('create', {'kind': 'version'}, {'title': 'Next', 'number': '0.2.X'})['entity']
        self.change('reorder', {'kind': 'version'}, {'ids': [another['id'], version_id]})
        self.assertEqual(self.request('list', collection='versions')['items'][0]['id'], another['id'])
        with self.assertRaises(RoadmapFault):
            self.change('delete', {'kind': 'version', 'id': version_id}, {'confirm': True})
        self.change('set_current', {'kind': 'version', 'id': another['id']})
        self.change('delete', items[0], {'confirm': True})
        self.assertEqual(self.request('notes', target=items[1])['notes'], 'Final notes')
        self.change('delete', reference, {'confirm': True})
        self.assertEqual(self.request('list', collection='subversions', versionId=version_id)['items'], [])
        self.change('delete', {'kind': 'version', 'id': version_id}, {'confirm': True})
        self.assertEqual(self.request('overview')['roadmap']['notes'], 'Root notes')

    def test_original_receipts_stale_revisions_current_binding_and_foreign_ids(self):
        root = self.initialize(); ref = {'kind': 'version', 'id': root['currentVersionId']}
        body = self.body('append_notes', ref, {'notes': 'First'})
        accepted = self.request('mutate', input=body)
        self.change('append_notes', ref, {'notes': 'Second'})
        self.assertEqual(self.request('mutate', input=body), accepted)
        self.assertEqual(self.request('notes', target=ref)['notes'], 'First\nSecond')
        for changed in [{**body, 'input': {'notes': 'Different'}}, {**body, 'requestId': str(uuid.uuid4())}]:
            with self.assertRaises(RoadmapFault) as error:
                self.request('mutate', input=changed)
            self.assertEqual(error.exception.code, 409)
        other = self.initialize(self.ids[1])
        with self.assertRaises(RoadmapFault) as error:
            self.change('update', {'kind': 'version', 'id': other['currentVersionId']}, {'title': 'Foreign'})
        self.assertEqual(error.exception.code, 404)
        another = self.change('create', {'kind': 'version'}, {'title': 'Next'})['entity']
        self.change('set_current', {'kind': 'version', 'id': another['id']})
        stale = self.body('append_notes', ref, {'notes': 'Wrong current'})
        stale['currentVersionId'] = root['currentVersionId']
        with self.assertRaises(RoadmapFault) as error:
            self.request('mutate', input=stale)
        self.assertEqual(error.exception.code, 409)
        self.assertEqual(self.request('notes', target=ref)['notes'], 'First\nSecond')

    def test_concurrent_notes_report_conflict_and_preserve_both_on_reconciled_retry(self):
        root = self.initialize(); ref = {'kind': 'version', 'id': root['currentVersionId']}
        bodies = [self.body('append_notes', ref, {'notes': text}, binding=root) for text in ['Alpha', 'Beta']]
        def submit(body):
            try:
                return self.request('mutate', input=body)
            except RoadmapFault as error:
                return error
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, bodies))
        conflicts = [i for i, result in enumerate(results) if isinstance(result, RoadmapFault)]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(results[conflicts[0]].code, 409)
        retry = {**bodies[conflicts[0]], 'expectedRevision': self.request('overview')['roadmap']['revision']}
        self.request('mutate', input=retry)
        self.assertEqual(set(self.request('notes', target=ref)['notes'].splitlines()), {'Alpha', 'Beta'})

    def test_revision_and_project_bound_pages_and_parent_checks(self):
        root = self.initialize()
        self.change('create', {'kind': 'version'}, {'title': 'Second'})
        page = self.request('list', collection='versions', limit=1)
        next_page = self.request('list', collection='versions', limit=1, cursor=page['nextCursor'])
        self.assertNotEqual(page['items'][0]['id'], next_page['items'][0]['id'])
        self.initialize(self.ids[1])
        with self.assertRaises(RoadmapFault) as error:
            self.request('list', self.ids[1], collection='versions', cursor=page['nextCursor'])
        self.assertEqual(error.exception.code, 409)
        self.change('append_notes', {'kind': 'roadmap', 'id': root['id']}, {'notes': 'Changed'})
        with self.assertRaises(RoadmapFault) as error:
            self.request('list', collection='versions', cursor=page['nextCursor'])
        self.assertEqual(error.exception.code, 409)
        sub = self.change('create', {'kind': 'subversion', 'versionId': root['currentVersionId']}, {'title': 'Sub'})['entity']
        other_version = next_page['items'][0]['id']
        with self.assertRaises(RoadmapFault) as error:
            self.request('get', target={'kind': 'subversion', 'id': sub['id'], 'versionId': other_version})
        self.assertEqual(error.exception.code, 404)

    def test_invalid_fields_formats_statuses_and_oversized_append_do_not_change_state(self):
        root = self.initialize(); ref = {'kind': 'version', 'id': root['currentVersionId']}
        before = self.request('overview')
        invalid = [self.body('update', ref, {'title': ''}), self.body('update', ref, {'path': '/etc'}),
                   self.body('update', ref, {'status': 'done'}), self.body('replace_notes', ref, {'notes': '\0'}),
                   self.body('create', {'kind': 'version'}, {'title': 'Bad', 'number': '00.2.X'}),
                   self.body('create', {'kind': 'subversion', 'versionId': ref['id']}, {'title': 'Bad', 'number': '0.9.1'})]
        for body in invalid:
            with self.assertRaises(RoadmapFault) as error:
                self.request('mutate', input=body)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.request('overview'), before)
        self.change('replace_notes', ref, {'notes': 'x' * 32768})
        revision = self.request('overview')['roadmap']['revision']
        with self.assertRaises(RoadmapFault):
            self.change('append_notes', ref, {'notes': 'Too much'})
        self.assertEqual(self.request('overview')['roadmap']['revision'], revision)
        self.assertEqual(len(self.request('notes', target=ref)['notes']), 32768)


if __name__ == '__main__':
    unittest.main()
