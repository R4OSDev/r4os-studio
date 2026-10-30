"""Local preferences/provenance and real session persistence; no tool effects."""
from contextlib import closing
import json
import unittest
from unittest.mock import patch
import uuid
import test_runs as fixtures
from profile import PROFILE, NOTES_SKILL_PROFILE, permission_tools
from session_store import SessionStore, encode, operation
from run_store import admit, get_run, transition
from tool_defaults import permissions, repository_binding


class Defaults(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def binding(self):
        value = {'schema': 1, 'revision': 1, 'connectionId': str(uuid.uuid4()), 'userId': 7,
                 'repository': {'id': 11, 'owner': 'own', 'name': 'app'}, 'branch': 'main'}
        root = self.projects / self.pid / '.studio/git'; root.mkdir(parents=True, exist_ok=True)
        (root / 'binding.json').write_text(encode(value))
        return root, value

    def create(self, store, request=None):
        return store.create(request or {'name': 'New', 'providerId': self.provider, 'model': 'fixture', 'effort': 'low', 'requestId': str(uuid.uuid4())}, self.providers)

    def test_context_defaults_original_replay_explicit_off_and_frozen_runs(self):
        with self.open() as store, patch('session_store.engine', return_value={'profile': PROFILE, 'available': True}):
            original = tuple(store.row(self.sid))
            # Portable repository content grants no local permission.
            portable = store.workspace / '.r4os-studio'; portable.mkdir()
            (portable / 'project.json').write_text(encode({'permissions': {'studio.push_project': True}, 'repository': 'untrusted'}))
            local = self.create(store)
            self.assertFalse(local['permissions']['studio.push_project'])
            self.assertTrue(all(v for k, v in local['permissions'].items() if k != 'studio.push_project'))
            root, _ = self.binding()
            request = {'name': 'Bound', 'providerId': self.provider, 'model': 'fixture', 'effort': 'low', 'requestId': str(uuid.uuid4())}
            connected = self.create(store, request)
            self.assertTrue(all(connected['permissions'].values()))
            for key in ('environmentNotesEnabled', 'roadmapEnabled', 'webSearchEnabled', 'imageGenerationEnabled'): self.assertTrue(connected[key])
            root.joinpath('binding.json').unlink()
            self.assertEqual(self.create(store, request)['permissions'], connected['permissions'])
            disabled = store.update(connected['id'], {'revision': connected['revision'], 'permissions': {key: False for key in connected['permissions']}, 'environmentNotesEnabled': False, 'imageGenerationEnabled': False, 'webSearchEnabled': False, 'roadmapEnabled': False}, self.providers)
            self.assertFalse(any(disabled['permissions'].values()))
            run, _ = admit(store, connected['id'], {'requestId': str(uuid.uuid4()), 'revision': disabled['revision'], 'text': 'Own admission', 'environmentNotesSettings': 1, 'roadmapSettings': 1}, self.providers)
            frozen = json.loads(get_run(store, run['id'])['config'])
            self.binding()
            self.assertEqual(json.loads(get_run(store, run['id'])['config']), frozen)
            self.assertFalse(any(frozen['permissions'].values()))
            transition(store, run['id'], 'completed')
            self.assertEqual(store.get(connected['id'])['permissions'], disabled['permissions'])
            self.assertEqual(tuple(store.row(self.sid)), original)
        result = operation(self.projects, self.r4os, self.providers, {'operation': 'options', 'projectId': self.pid})
        self.assertTrue(all(t['defaultEnabled'] for t in result['tools']))

    def test_uncertain_creation_malformed_and_linked_private_binding_do_not_enable_push(self):
        with self.open() as store:
            root, value = self.binding(); request = str(uuid.uuid4())
            marker = root / 'create-repository.json'
            marker.write_text(encode({'state': 'intent', 'requestId': request}))
            self.assertFalse(permissions(store)['studio.push_project'])
            marker.write_text(encode({'state': 'created', 'requestId': request, 'repositoryId': 11}))
            job_dir = self.projects / '.studio/github/Jobs' / request; job_dir.mkdir(parents=True)
            job = {'projectId': self.pid, 'kind': 'create_repository', 'state': 'unknown', 'result': {'binding': value}}
            for state in ('unknown', 'failed', 'running', 'completed'):
                (job_dir / 'job.json').write_text(encode({**job, 'state': state}))
                self.assertEqual(permissions(store)['studio.push_project'], state == 'completed')
            marker.unlink()
            root.joinpath('binding.json').write_text('[]')
            self.assertIsNone(repository_binding(store))
            root.joinpath('binding.json').unlink(); root.joinpath('binding.json').symlink_to(store.workspace / 'module.R4MF')
            self.assertIsNone(repository_binding(store))

    def test_new_skill_has_only_its_supported_permissions_and_features(self):
        import test_skills
        fixture = test_skills.Skills(); fixture.setUp()
        try:
            with closing(SessionStore(fixture.projects, fixture.r4os, fixture.ids[0], 'skill')) as store, patch('session_store.engine', return_value={'profile': NOTES_SKILL_PROFILE, 'available': True}):
                value = store.create(fixture.settings(), fixture.providers)
                self.assertEqual(set(value['permissions']), {'studio.' + t for t in permission_tools(NOTES_SKILL_PROFILE)})
                self.assertTrue(all(value['permissions'].values()))
                self.assertNotIn('roadmapEnabled', value)
                self.assertNotIn('studio.push_project', value['permissions'])
                self.assertNotIn('studio.read_environment_notes', value['permissions'])
                self.assertNotIn('image_gen.imagegen', value['permissions'])
                self.assertTrue(value['environmentNotesEnabled']); self.assertTrue(value['imageGenerationEnabled'])
        finally: fixture.tearDown()


if __name__ == '__main__': unittest.main()
