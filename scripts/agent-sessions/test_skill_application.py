"""Defaults, atomic exceptions, frozen resources and unchanged native declarations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import uuid

import test_skills as fixtures
from profile import SKILL_PROFILE, LEGACY_TOOLS
from run_store import admit, get_run, transition
from session_store import SessionStore, encode
from store import ProjectFault, connect
from tool_catalog import specifications
from worker import Worker
from instructions import compose
import skill_application as application


class Application(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.Skills(); self.fixture.setUp(); f = self.fixture
        self.publish(f.ids[0], 'First published body.')
        with f.open(f.ids[1]) as store, patch('session_store.engine', return_value=f.engine):
            self.session = store.create(f.settings(), f.providers)

    def tearDown(self): self.fixture.tearDown()
    def open(self): return self.fixture.open(self.fixture.ids[1])
    def publish(self, ident, body):
        f = self.fixture
        fixtures.packages.atomic(f.skills / ident / 'Workspace/SKILL.md',
            ('---\nname: application-test\ndescription: Handle the requested application test.\n---\n\n'+body+'\n').encode())
        with closing(fixtures.packages.connect(f.skills)) as db:
            current = fixtures.packages.detail(db, f.skills, ident)
            return fixtures.packages.publish(db, f.skills, {'id': ident, 'revision': current['skill']['revision'],
                'draftHash': current['draftHash'], 'requestId': str(uuid.uuid4())}, '/usr/bin/node')
    def admit(self, store, request=None):
        data = request or {'requestId': str(uuid.uuid4()), 'revision': store.get(self.session['id'])['revision'], 'text': 'Use available skills.', 'skillSelection': 1}
        run, fresh = admit(store, self.session['id'], data, self.fixture.providers)
        return run, json.loads(get_run(store, run['id'])['config']), data, fresh
    def manifest(self, run):
        f = self.fixture
        return {**f.config, 'ownerType': 'skill', 'ownerId': f.ids[1], 'sessionId': self.session['id'], 'runId': run['id'], 'release': 'fixture', 'version': '0.4.9'}

    async def test_atomic_exceptions_revisions_and_legacy_settings_preserve_the_auxiliary_store(self):
        f = self.fixture; ident = f.ids[0]
        with self.open() as store:
            self.assertEqual(store.get(self.session['id'])['skillOverrides'], {})
            self.assertFalse((f.skills / 'SessionSettings.sqlite').exists())
            saved = store.update(self.session['id'], {'revision': 1, 'skillOverrides': {ident: False}}, f.providers)
            self.assertEqual(saved['revision'], 2); self.assertEqual(saved['skillOverrides'], {ident: False})
            saved = store.update(self.session['id'], {'revision': 2, 'name': 'Renamed'}, f.providers)
            self.assertEqual(saved['skillOverrides'], {ident: False})
            saved = store.update(self.session['id'], {'revision': 3, 'skillOverrides': {ident: True}}, f.providers)
            self.assertEqual(saved['revision'], 4); self.assertEqual(saved['skillOverrides'], {})
            with self.assertRaises(ProjectFault): store.update(self.session['id'], {'revision': 3, 'skillOverrides': {ident: False}}, f.providers)
            with self.assertRaises(ProjectFault): store.update(self.session['id'], {'revision': 4, 'skillOverrides': {str(uuid.uuid4()): False}}, f.providers)
            self.assertEqual(store.get(self.session['id'])['revision'], 4)
            self.assertNotIn('skillOverrides', json.loads(store.row(self.session['id'])['settings']))
            self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0], 1)
        def save(ident):
            try:
                with self.open() as store: return store.update(self.session['id'], {'revision': 4, 'skillOverrides': {ident: False}}, f.providers)
            except ProjectFault: return None
        with ThreadPoolExecutor(2) as executor: replies = list(executor.map(save, f.ids))
        winner = next(value for value in replies if value is not None); self.assertEqual(sum(value is not None for value in replies), 1)
        with self.open() as store:
            self.assertEqual(store.get(self.session['id'])['skillOverrides'], winner['skillOverrides'])
            # An old version writes only its original basic settings JSON.
            with store.db: store.db.execute('UPDATE sessions SET revision=revision+1 WHERE id=?', (self.session['id'],))
        with self.open() as store: self.assertEqual(store.get(self.session['id'])['skillOverrides'], winner['skillOverrides'])

    async def test_owner_type_and_owner_id_keep_same_session_ids_independent(self):
        f = self.fixture
        with self.open() as store: store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[0]: False}}, f.providers)
        # Same owner UUID/session UUID in a project is a different typed owner.
        with closing(connect(f.projects)) as db, db:
            db.execute("INSERT INTO projects VALUES (?,?,'','C','terminal',?,NULL,'{}','now','now',1,'ready')", (f.ids[1], 'Project fixture', 'fixture'))
        workspace = f.projects / f.ids[1] / 'Workspace'; workspace.mkdir(parents=True); (workspace / 'module.R4MF').write_text('R4OS_MODULE_MANIFEST=2\n')
        with closing(SessionStore(f.projects, f.r4os, f.ids[1])) as store:
            settings = {key: self.session[key] for key in ('providerId', 'model', 'effort', 'fastMode')}
            settings['permissions'] = {'studio.'+name: True for name in LEGACY_TOOLS}
            with store.db: store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')", (self.session['id'], f.ids[1], 'Project', encode(settings), encode({**f.engine, 'profile': 'studio-tools-v1'})))
            self.assertEqual(store.get(self.session['id'])['skillOverrides'], {})
            store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[1]: False}}, f.providers)
        with self.open() as store: self.assertEqual(store.get(self.session['id'])['skillOverrides'], {f.ids[0]: False})

    async def test_admitted_revisions_names_and_defaults_for_new_skills_are_frozen(self):
        f = self.fixture
        before = sorted(path.name for path in (f.skills / f.ids[1] / 'Workspace').iterdir())
        with self.open() as store:
            run, frozen, request, _ = self.admit(store)
            self.assertEqual([entry['id'] for entry in frozen['skillAccess']['entries']], [f.ids[0]])
            self.assertEqual(frozen['skillAccess']['unavailable'][0]['id'], f.ids[1])
            self.assertNotIn(str(f.root), compose(frozen))
            with self.assertRaises(ProjectFault): store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[0]: False}}, f.providers)
        with closing(fixtures.packages.connect(f.skills)) as db:
            current = fixtures.packages.detail(db, f.skills, f.ids[0])
            fixtures.packages.rename_skill(db, f.skills, {'id': f.ids[0], 'revision': current['skill']['revision'], 'name': 'Renamed global skill'})
        updated = self.publish(f.ids[0], 'Second published body.')
        extra = str(uuid.uuid4())
        with closing(fixtures.packages.connect(f.skills)) as db: fixtures.packages.create(db, f.skills, {'id': extra, 'name': 'New global skill'})
        self.publish(extra, 'New skill in an older session.')
        with self.open() as store:
            self.assertNotEqual(frozen['skillAccess']['entries'][0]['activeHash'], updated['skill']['activeHash'])
            self.assertEqual(json.loads(get_run(store, run['id'])['config']), frozen)
            transition(store, run['id'], 'completed')
            again, original, _, fresh = self.admit(store, request); self.assertFalse(fresh); self.assertEqual(original, frozen); self.assertEqual(again['id'], run['id'])
            _, current, _, _ = self.admit(store)
            self.assertEqual({entry['id'] for entry in current['skillAccess']['entries']}, {f.ids[0], extra})
            self.assertEqual(current['skillAccess']['entries'][0]['name'], 'Renamed global skill')
        self.assertEqual(sorted(path.name for path in (f.skills / f.ids[1] / 'Workspace').iterdir()), before)
        self.assertFalse(any(path.name.startswith('__studio_skills__') for path in (f.skills / f.ids[1] / 'Workspace').iterdir()))

    async def test_limits_and_changed_published_revisions_fail_without_admitting_inference(self):
        with self.open() as store:
            for limit, value in [('MAX_ACTIVE', 0), ('MAX_CATALOG', 1), ('MAX_RESOURCES', 1)]:
                with patch.object(application, limit, value):
                    with self.assertRaises(ProjectFault): self.admit(store)
                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        f = self.fixture
        with closing(fixtures.packages.connect(f.skills)) as db: current = fixtures.packages.detail(db, f.skills, f.ids[0])
        source = f.skills / f.ids[0] / 'Revisions' / current['skill']['activeHash'] / 'Workspace/SKILL.md'
        source.write_text('Preserve externally changed snapshot')
        with self.open() as store:
            with self.assertRaises(ProjectFault): self.admit(store)
            saved = store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[0]: False}}, f.providers)
            self.assertEqual(saved['skillOverrides'], {f.ids[0]: False})
            _, frozen, _, _ = self.admit(store); self.assertEqual(frozen['skillAccess']['entries'], [])
        self.assertEqual(source.read_text(), 'Preserve externally changed snapshot')

    async def test_virtual_paths_preserve_existing_workspace_entries_and_corrupt_choices_preserve_bytes(self):
        f = self.fixture; workspace = f.skills / f.ids[1] / 'Workspace'
        existing = workspace / '__studio_skills__'; existing.mkdir(); (existing / 'user.txt').write_text('User content retained')
        with self.open() as store:
            run, frozen, _, _ = self.admit(store)
            self.assertEqual(frozen['skillAccess']['alias'], '__studio_skills__2')
            self.assertEqual((existing / 'user.txt').read_text(), 'User content retained')
            self.assertFalse((workspace / '__studio_skills__2').exists())
            transition(store, run['id'], 'completed')
            store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[0]: False}}, f.providers)
        preferences = f.skills / 'SessionSettings.sqlite'; preferences.write_bytes(b'preserve corrupt session choices')
        with self.open() as store:
            with self.assertRaises(ProjectFault) as failure: store.get(self.session['id'])
            self.assertEqual(failure.exception.code, 503)
            self.assertEqual(store.history(self.session['id'])['items'][0]['type'], 'user')
        self.assertEqual(preferences.read_bytes(), b'preserve corrupt session choices')

    async def test_same_native_thread_receives_current_catalogue_without_changed_declarations(self):
        f = self.fixture; seen = []
        class Native:
            def __init__(self, args, notify, tool): self.notify = notify
            async def start(self): pass
            async def close(self): pass
            async def request(self, method, params, **kwargs):
                seen.append((method, params))
                if method.startswith('thread/'): return {'thread': {'id': 'same-selected-skill-thread'}}
                if method == 'turn/start':
                    await self.notify('turn/completed', {'threadId': 'same-selected-skill-thread', 'turn': {'id': 'turn', 'status': 'completed'}})
                    return {'turn': {'id': 'turn'}}
                return {}
        with self.open() as store: first, _, _, _ = self.admit(store)
        worker = Worker(self.manifest(first))
        with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', Native): await worker.run()
        with self.open() as store:
            store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[0]: False}}, f.providers)
            second, _, _, _ = self.admit(store)
        worker = Worker(self.manifest(second))
        with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', Native): await worker.run()
        start = next(params for method, params in seen if method == 'thread/start')
        resumed = next(params for method, params in seen if method == 'thread/resume')
        self.assertIn(f.ids[0], start['baseInstructions']); self.assertNotIn(f.ids[0], resumed['baseInstructions'])
        self.assertEqual(resumed['threadId'], 'same-selected-skill-thread')
        self.assertEqual(start['dynamicTools'], specifications(f.engine['profile']))
        roots = next(value for value in specifications('studio-tools-v1') if value['name'] == 'studio_read_file')['inputSchema']['properties']['root']['enum']
        self.assertEqual(roots, ['workspace', 'sdk', 'contract', 'zig', 'rust'])

    @unittest.skipIf(os.getuid() == 0, 'Run real readonly resource namespace as the unprivileged service user.')
    async def test_real_readonly_broker_needs_no_sdk_and_rejects_disabled_resources_and_receipt_replay(self):
        f = self.fixture
        self.publish(f.ids[1], 'Second global body.')
        with self.open() as store:
            settings = json.loads(store.row(self.session['id'])['settings']); settings['permissions'] = {'studio.'+name: True for name in LEGACY_TOOLS}
            with store.db: store.db.execute('UPDATE sessions SET settings=?,engine=? WHERE id=?', (encode(settings), encode({**f.engine, 'profile': SKILL_PROFILE}), self.session['id']))
            store.update(self.session['id'], {'revision': 1, 'skillOverrides': {f.ids[1]: False}}, f.providers)
            run, config, _, _ = self.admit(store)
        worker = Worker(self.manifest(run)); worker.thread_id = 'thread'; worker.turn_id = 'turn'
        path = config['skillAccess']['alias'] + '/' + f.ids[0] + '/SKILL.md'
        async def call(name, args, call_id=None):
            native = await worker.tool({'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_'+name, 'arguments': args, 'callId': call_id or str(uuid.uuid4())})
            return json.loads(native['contentItems'][0]['text'])
        try:
            first = await call('read_file', {'root': 'workspace', 'path': path}, 'resource-receipt')
            self.assertTrue(first['success'], first); self.assertIn('First published body.', first['output']); self.assertIsNone(worker.sandbox.context)
            self.assertEqual((await call('write_file', {'path': path, 'content': 'must not write', 'expectedSha256': first['sha256']}))['error'], 'readOnly')
            self.assertEqual((await call('apply_patch', {'patch': '*** Begin Patch\n*** Update File: '+path+'\n@@\n-bad\n+worse\n*** End Patch', 'expectedHashes': {path: first['sha256']}}))['error'], 'readOnly')
            disabled = config['skillAccess']['alias'] + '/' + f.ids[1] + '/SKILL.md'
            self.assertEqual((await call('read_file', {'path': disabled}))['error'], 'unavailable')
            self.assertEqual((await call('read_file', {'path': path+'/../../secret'}))['error'], 'fileError')
            self.assertFalse((worker.store.workspace / config['skillAccess']['alias']).exists())
            transition(worker.store, run['id'], 'completed')
        finally: await worker.cleanup(); worker.store.close()
        with self.open() as store:
            store.update(self.session['id'], {'revision': 2, 'skillOverrides': {f.ids[0]: False, f.ids[1]: False}}, f.providers)
            run, _, _, _ = self.admit(store)
        worker = Worker(self.manifest(run)); worker.thread_id = 'thread'; worker.turn_id = 'turn'
        try:
            self.assertEqual((await call('read_file', {'root': 'workspace', 'path': path}, 'resource-receipt'))['error'], 'unavailable')
            self.assertEqual((await call('read_file', {'root': 'workspace', 'path': path}))['error'], 'unavailable')
            self.assertIsNone(worker.sandbox.context)
            transition(worker.store, run['id'], 'completed')
        finally: await worker.cleanup(); worker.store.close()
        with self.open() as store:
            permissions = store.get(self.session['id'])['permissions'] | {'studio.read_file': False}
            store.update(self.session['id'], {'revision': 3, 'skillOverrides': {f.ids[1]: False}, 'permissions': permissions}, f.providers)
            run, _, _, _ = self.admit(store)
        worker = Worker(self.manifest(run)); worker.thread_id = 'thread'; worker.turn_id = 'turn'
        try:
            self.assertEqual((await call('read_file', {'root': 'workspace', 'path': path}))['error'], 'disabled')
            self.assertIsNone(worker.skill_resources.view)
        finally: await worker.cleanup(); worker.store.close()


if __name__ == '__main__': unittest.main()
