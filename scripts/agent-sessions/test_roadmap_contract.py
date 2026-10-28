"""Regress real rejected calls, backend parity and preserved native conversations."""
import hashlib
import json
import unittest
import uuid

import test_roadmap_tools as fixtures
from instructions import compose
from profile import PROFILE
from tool_catalog import specifications, validate_arguments


LEGACY_HASHES = {
    **fixtures.BASELINES,
    'studio-tools-v9': 'f9f33dab160f465c381c1055903d37e0a1f3543a9cbe28c556901208feb15efa',
    'studio-tools-v10': 'e0eba722f01a37e9ca6531b307e39cd2fb68cb756f79c840b3e2104b52b414a6',
    'studio-tools-v11': '97b05189a803ac8d1a071f4bf216bc13e5072c83a68fe325f50cc8cedb7a2166',
    'studio-skill-tools-v3': '60886ee320f317fdfaca3a4ba3385ed7a8ea95c1bf9396c3b3b3437edd629517',
    'studio-skill-tools-v4': 'deadd6059762c5c5c2ab6c4cebaf74d06d93cf3e2b5182c799f9c54203104505',
}


class RoadmapContractTest(unittest.IsolatedAsyncioTestCase):
    open = fixtures.RoadmapToolsTest.open
    setUp = fixtures.RoadmapToolsTest.setUp
    tearDown = fixtures.RoadmapToolsTest.tearDown
    start = fixtures.RoadmapToolsTest.start
    finish = fixtures.RoadmapToolsTest.finish
    call = fixtures.RoadmapToolsTest.call
    good = fixtures.RoadmapToolsTest.good

    def test_existing_declarations_and_permissions_are_preserved(self):
        self.assertEqual(PROFILE, 'studio-tools-v12')
        for profile, expected in LEGACY_HASHES.items():
            actual = hashlib.sha256(json.dumps(specifications(profile), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(actual, expected, profile)
        old = {value['name']: value for value in specifications('studio-tools-v11')}
        current = {value['name']: value for value in specifications(PROFILE)}
        self.assertEqual(set(old), set(current))
        for name in old:
            if name not in ('studio_read_roadmap', 'studio_update_roadmap'):
                self.assertEqual(old[name], current[name], name)

    async def test_four_observed_invalid_calls_fail_clearly_before_effect_and_corrected_calls_save(self):
        worker = self.start()
        await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})
        state = await self.good(worker, 'read_roadmap', {'view': 'current'})
        version = state['currentVersionId']
        arguments = {'operation': 'mutate', 'requestId': str(uuid.uuid4()), 'expectedRevision': state['revision'],
                     'currentVersionId': version, 'action': 'create', 'target': {'kind': 'subversion', 'versionId': version},
                     'input': {'title': 'First playable block world'}}
        state = await self.good(worker, 'update_roadmap', arguments)
        parent = {'kind': 'task', 'versionId': version, 'subversionId': state['entity']['id']}
        revision = state['revision']
        bad_inputs = ({'title': 'Platform', 'description': 'Inspect the pinned SDK.', 'status': 'open'},
                      {'title': 'Platform', 'notes': 'Inspect the pinned SDK.', 'status': 'open'}, {'title': 'Platform'})
        for content in bad_inputs:
            arguments = {'operation': 'mutate', 'requestId': str(uuid.uuid4()), 'expectedRevision': revision,
                         'currentVersionId': version, 'action': 'create', 'target': parent, 'input': content}
            result = await self.call(worker, 'update_roadmap', arguments)
            self.assertEqual(result['error'], 'invalidArguments', result)
            self.assertIn('arguments.input', result['output']); self.assertIn('title', result['output'])
            self.assertIn('description', result['output'])
        result = await self.call(worker, 'read_roadmap', {'view': 'overview', 'expectedRevision': revision})
        self.assertEqual(result['error'], 'invalidArguments', result)
        self.assertIn('expectedRevision', result['output']); self.assertIn('allowed fields', result['output'])
        state = await self.good(worker, 'read_roadmap', {'view': 'revision'})
        self.assertEqual(state['revision'], revision)
        await self.good(worker, 'read_roadmap', {'view': 'overview'})
        task = await self.good(worker, 'update_roadmap', {'operation': 'mutate', 'requestId': str(uuid.uuid4()),
            'expectedRevision': revision, 'currentVersionId': version, 'action': 'create', 'target': parent,
            'input': {'description': 'Inspect the pinned SDK.', 'notes': 'Preserve pins.', 'status': 'open'}})
        self.assertEqual(task['revision'], revision + 1)
        text = await self.good(worker, 'read_roadmap', {'view': 'text',
            'target': {**parent, 'id': task['entity']['id']}, 'field': 'description', 'expectedRevision': task['revision']})
        self.assertEqual(text['text'], 'Inspect the pinned SDK.')

    async def test_saved_v11_session_gets_precise_guidance_and_server_errors_without_profile_or_thread_change(self):
        with self.open() as store:
            store.db.execute('UPDATE sessions SET engine=?', (json.dumps({'profile': 'studio-tools-v11'}),)); store.db.commit()
        worker = self.start()
        self.assertEqual(worker.config['engine']['profile'], 'studio-tools-v11')
        frozen = json.dumps(worker.config, sort_keys=True)
        text = compose(worker.config)
        self.assertIn('There is NO title field', text)
        self.assertIn('expectedRevision is supported ONLY for this view', text)
        self.assertEqual(json.dumps(worker.config, sort_keys=True), frozen)
        await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})
        result = await self.call(worker, 'read_roadmap', {'view': 'overview', 'expectedRevision': 1})
        self.assertEqual(result['error'], 'failed', result)
        self.assertIn('view=overview', result['output']); self.assertIn('expectedRevision', result['output'])
        self.assertIn('view=text', result['output'])
        state = await self.good(worker, 'read_roadmap', {'view': 'current'})
        sub = await self.good(worker, 'update_roadmap', {'operation': 'mutate', 'requestId': str(uuid.uuid4()),
            'expectedRevision': state['revision'], 'currentVersionId': state['currentVersionId'], 'action': 'create',
            'target': {'kind': 'subversion', 'versionId': state['currentVersionId']}, 'input': {'title': 'Shared'}})
        result = await self.call(worker, 'update_roadmap', {'operation': 'mutate', 'requestId': str(uuid.uuid4()),
            'expectedRevision': sub['revision'], 'currentVersionId': state['currentVersionId'], 'action': 'create',
            'target': {'kind': 'task', 'versionId': state['currentVersionId'], 'subversionId': sub['entity']['id']},
            'input': {'title': 'Not supported', 'description': 'Use this text.'}})
        self.assertIn('task create input', result['output']); self.assertIn('title', result['output'])
        self.assertIn('description', result['output']); self.assertEqual(result['roadmap']['code'], 400)
        current = await self.good(worker, 'read_roadmap', {'view': 'revision'})
        self.assertEqual(current['revision'], sub['revision'])
        self.assertEqual(worker.config['engine']['profile'], 'studio-tools-v11')

    def test_views_parents_statuses_and_action_inputs_cannot_be_mixed(self):
        ident = str(uuid.uuid4())
        for arguments in ({'view': 'current', 'expectedRevision': 1}, {'view': 'tasks', 'subversionId': ident},
                          {'view': 'entry', 'target': {'kind': 'task', 'id': ident}},
                          {'view': 'text', 'target': {'kind': 'task', 'versionId': ident, 'subversionId': ident, 'id': ident}, 'field': 'vision'}):
            with self.assertRaises(ValueError): validate_arguments('read_roadmap', arguments)
        base = {'operation': 'mutate', 'requestId': ident, 'expectedRevision': 1, 'currentVersionId': ident}
        for arguments in (
            {'action': 'create', 'target': {'kind': 'version'}, 'input': {'description': 'Not a title'}},
            {'action': 'create', 'target': {'kind': 'version'}, 'input': {'notes': 'Missing the title'}},
            {'action': 'create', 'target': {'kind': 'task', 'versionId': ident, 'subversionId': ident}, 'input': {'notes': 'Missing the description'}},
            {'action': 'update', 'target': {'kind': 'version', 'id': ident}, 'input': {'status': 'done'}},
            {'action': 'update', 'target': {'kind': 'version', 'id': ident}, 'input': {}},
            {'action': 'append_notes', 'target': {'kind': 'version', 'id': ident}, 'input': {'notes': 'Evidence', 'title': 'Extra'}},
            {'action': 'delete', 'target': {'kind': 'version', 'id': ident}, 'input': {'confirm': False}},
            {'action': 'reorder', 'target': {'kind': 'subversion', 'id': ident, 'versionId': ident}, 'input': {'ids': []}}):
            with self.assertRaises(ValueError): validate_arguments('update_roadmap', {**base, **arguments})
