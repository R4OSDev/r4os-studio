"""Regress real rejected calls, backend parity and preserved native conversations."""
import json
import unittest
import uuid

import test_roadmap_tools as fixtures
from instructions import compose
from profile import PROFILE, ROADMAP_TOOLS, permission_tools
from tool_catalog import validate_arguments


class RoadmapContractTest(unittest.IsolatedAsyncioTestCase):
    open = fixtures.RoadmapToolsTest.open
    setUp = fixtures.RoadmapToolsTest.setUp
    tearDown = fixtures.RoadmapToolsTest.tearDown
    start = fixtures.RoadmapToolsTest.start
    finish = fixtures.RoadmapToolsTest.finish
    call = fixtures.RoadmapToolsTest.call
    good = fixtures.RoadmapToolsTest.good


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
        self.assertEqual(json.loads(worker.store.row(self.sid)['engine'])['profile'], 'studio-tools-v11')
        frozen = json.dumps(worker.config, sort_keys=True)
        text = compose(worker.config)
        self.assertIn('There is NO title field', text)
        self.assertIn('expectedRevision is supported ONLY for this view', text)
        self.assertEqual(json.dumps(worker.config, sort_keys=True), frozen)
        await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})
        result = await self.call(worker, 'read_roadmap', {'view': 'overview', 'expectedRevision': 1})
        self.assertEqual(result['error'], 'invalidArguments', result)
        self.assertIn('expectedRevision', result['output']); self.assertIn('allowed fields', result['output'])
        state = await self.good(worker, 'read_roadmap', {'view': 'current'})
        sub = await self.good(worker, 'update_roadmap', {'operation': 'mutate', 'requestId': str(uuid.uuid4()),
            'expectedRevision': state['revision'], 'currentVersionId': state['currentVersionId'], 'action': 'create',
            'target': {'kind': 'subversion', 'versionId': state['currentVersionId']}, 'input': {'title': 'Shared'}})
        result = await self.call(worker, 'update_roadmap', {'operation': 'mutate', 'requestId': str(uuid.uuid4()),
            'expectedRevision': sub['revision'], 'currentVersionId': state['currentVersionId'], 'action': 'create',
            'target': {'kind': 'task', 'versionId': state['currentVersionId'], 'subversionId': sub['entity']['id']},
            'input': {'title': 'Not supported', 'description': 'Use this text.'}})
        self.assertEqual(result['error'], 'invalidArguments', result)
        self.assertIn('title', result['output']); self.assertIn('description', result['output'])
        current = await self.good(worker, 'read_roadmap', {'view': 'revision'})
        self.assertEqual(current['revision'], sub['revision'])
        self.assertEqual(json.loads(worker.store.row(self.sid)['engine'])['profile'], 'studio-tools-v11')

    def test_views_parents_statuses_and_action_inputs_cannot_be_mixed(self):
        self.assertFalse(set(ROADMAP_TOOLS) & set(permission_tools(PROFILE)))
        ident = str(uuid.uuid4())
        for arguments in ({'view': 'current', 'path': '/etc'}, {'view': 'current', 'projectId': ident},
                          {'view': 'current', 'expectedRevision': 1}, {'view': 'tasks', 'subversionId': ident},
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
