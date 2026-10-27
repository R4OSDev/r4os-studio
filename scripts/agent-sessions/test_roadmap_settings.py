"""Real isolated session persistence/admission; no model or host jobs."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import test_runs as fixtures
from profile import (PROFILE, ROADMAP_PROFILE, tools_for, default_enabled,
                     CODEX_VERSION, CODEX_SHA256)
from roadmap_access import require
from run_store import admit, get_run, transition
from session_store import encode
from store import ProjectFault


class RoadmapSettings(unittest.TestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def test_missing_value_read_is_additive_and_explicit_off_survives_reopen(self):
        with self.open() as store:
            before = tuple(store.db.execute('SELECT settings,engine,thread_id,revision FROM sessions').fetchone())
            session = store.get(self.sid)
            self.assertTrue(session['roadmapEnabled'])
            self.assertFalse(session['roadmapAccess']['available'])
            self.assertIn('New session required', session['roadmapAccess']['reason'])
            self.assertEqual(tuple(store.db.execute('SELECT settings,engine,thread_id,revision FROM sessions').fetchone()), before)
            changed = store.update(self.sid, {'revision': 1, 'roadmapEnabled': False}, self.providers)
            self.assertFalse(changed['roadmapEnabled'])
            self.assertEqual(changed['permissions'], self.settings['permissions'])
            self.assertEqual(changed['webSearchEnabled'], session['webSearchEnabled'])
            self.assertEqual(changed['engine'], session['engine'])
        with self.open() as store:
            self.assertFalse(store.get(self.sid)['roadmapEnabled'])
            with self.assertRaises(ProjectFault): store.update(self.sid, {'revision': 1, 'roadmapEnabled': True}, self.providers)
            for value in [1, 'false', None, []]:
                with self.assertRaises(ProjectFault): store.update(self.sid, {'revision': 2, 'roadmapEnabled': value}, self.providers)
            store.update(self.sid, {'revision': 2, 'name': 'Name only'}, self.providers)
            self.assertFalse(store.get(self.sid)['roadmapEnabled'])

    def test_new_sessions_on_and_old_native_profiles_threads_permissions_preserved(self):
        engine = {'profile': PROFILE, 'version': CODEX_VERSION, 'sha256': CODEX_SHA256, 'available': True}
        with self.open() as store, patch('session_store.engine', return_value=engine):
            new = store.create({'name': 'New', 'providerId': self.provider, 'model': 'fixture', 'effort': 'low', 'requestId': str(uuid.uuid4())}, self.providers)
            self.assertTrue(new['roadmapEnabled'])
            self.assertTrue(new['roadmapAccess']['available'])
            for n in range(1, 8):
                profile = 'studio-tools-v' + str(n)
                permissions = {'studio.' + t: default_enabled(t) for t in tools_for(profile)}
                settings = {**self.settings, 'permissions': permissions}
                store.db.execute('UPDATE sessions SET settings=?,engine=?,thread_id=? WHERE id=?',
                                 (encode(settings), encode({**engine, 'profile': profile}), 'original-' + profile, self.sid))
                store.db.commit()
                before = tuple(store.row(self.sid))
                self.assertTrue(store.get(self.sid)['roadmapEnabled'])
                self.assertEqual(tuple(store.row(self.sid)), before)
                saved = store.update(self.sid, {'revision': store.get(self.sid)['revision'], 'roadmapEnabled': False}, self.providers)
                self.assertEqual(saved['permissions'], permissions)
                self.assertEqual(saved['engine']['profile'], profile)
                self.assertEqual(store.row(self.sid)['thread_id'], 'original-' + profile)

    def test_concurrent_save_and_frozen_next_runs_do_not_rewrite_previous_admissions(self):
        def save(value):
            try:
                with self.open() as store: return store.update(self.sid, {'revision': 1, 'roadmapEnabled': value, 'name': 'Choice ' + str(value)}, self.providers)
            except ProjectFault: return None
        with ThreadPoolExecutor(2) as pool: replies = list(pool.map(save, [False, True]))
        self.assertEqual(sum(v is not None for v in replies), 1)
        with self.open() as store:
            rev = store.get(self.sid)['revision']
            off = store.update(self.sid, {'revision': rev, 'roadmapEnabled': False}, self.providers)
            run, _ = admit(store, self.sid, {**self.data, 'revision': off['revision'], 'roadmapSettings': 1}, self.providers)
            frozen = json.loads(get_run(store, run['id'])['config'])
            self.assertFalse(frozen['roadmapEnabled'])
            with self.assertRaises(ProjectFault): store.update(self.sid, {'revision': off['revision'], 'roadmapEnabled': True}, self.providers)
            transition(store, run['id'], 'completed')
            on = store.update(self.sid, {'revision': off['revision'], 'roadmapEnabled': True}, self.providers)
            other, _ = admit(store, self.sid, {**self.data, 'requestId': str(uuid.uuid4()), 'revision': on['revision']}, self.providers)
            self.assertTrue(json.loads(get_run(store, other['id'])['config'])['roadmapEnabled'])
            self.assertEqual(json.loads(get_run(store, run['id'])['config']), frozen)
            worker = SimpleNamespace(store=store, config=frozen)
            with self.assertRaises(ProjectFault): require(worker)
            worker.config = {**frozen, 'roadmapEnabled': True, 'engine': {'profile': ROADMAP_PROFILE}}
            with patch('roadmap_access.TOOLS_READY', False), self.assertRaises(ProjectFault): require(worker)
            with patch('roadmap_access.TOOLS_READY', True):
                require(worker)
                worker.config['owner'] = {'type': 'project', 'id': str(uuid.uuid4())}
                with self.assertRaises(ProjectFault): require(worker)

    def test_skill_sessions_cannot_store_or_gain_project_roadmap_access(self):
        import test_skills as skills
        fixture = skills.Skills()
        fixture.setUp()
        try:
            with fixture.open() as store:
                self.assertNotIn('roadmapEnabled', store.get(fixture.session['id']))
                for value in [False, True]:
                    with self.assertRaises(ProjectFault): store.update(fixture.session['id'], {'revision': 1, 'roadmapEnabled': value}, fixture.providers)
                run, _ = admit(store, fixture.session['id'], fixture.input(), fixture.providers)
                config = json.loads(get_run(store, run['id'])['config'])
                self.assertFalse(config['roadmapEnabled'])
                config.update(roadmapEnabled=True, engine={'profile': ROADMAP_PROFILE})
                with patch('roadmap_access.TOOLS_READY', True), self.assertRaises(ProjectFault):
                    require(SimpleNamespace(store=store, config=config))
        finally: fixture.tearDown()
