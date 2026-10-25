"""Real fixed publication helper under an inherited author lease; no inference."""
import asyncio
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from owner import open_lock
from profile import AUTHOR_PROFILE, SKILL_PROFILE, LEGACY_TOOLS, tools_for
from run_store import transition
from session_store import encode
import test_skills as fixtures
from worker import Worker
packages = fixtures.packages


class Authors(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.Skills(); self.fixture.setUp(); f = self.fixture
        f.projects.mkdir(exist_ok=True)
        self.run = f.admit(); self.worker = Worker(f.manifest(self.run)); self.worker.thread_id = 'thread'; self.worker.turn_id = 'turn'
        self.worker.lease = open_lock(f.projects, 'skill', f.ids[0]); fcntl.flock(self.worker.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        birth = (Path('/proc') / str(os.getpid()) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
        transition(self.worker.store, self.run['id'], 'running', worker={'pid': os.getpid(), 'birth': birth})

    async def asyncTearDown(self):
        await self.worker.cleanup()
        if self.worker.lease: self.worker.lease.close()
        self.worker.store.close(); self.fixture.tearDown()

    async def call(self, name, arguments=None, call_id=None):
        import uuid
        value = await self.worker.tool({'namespace': None, 'threadId': 'thread', 'turnId': 'turn', 'tool': 'studio_' + name,
            'arguments': arguments or {}, 'callId': call_id or str(uuid.uuid4())})
        return json.loads(value['contentItems'][0]['text'])

    def draft(self, suffix=''):
        workspace = self.worker.store.workspace
        packages.atomic(workspace / 'SKILL.md', ('---\nname: author-test\ndescription: Create a requested bounded QA report.\n---\n\n# Instructions\nUse supplied data.\n'+suffix).encode())
        scripts = workspace / 'scripts'; scripts.mkdir(exist_ok=True)
        packages.atomic(scripts / 'helper.py', b"from pathlib import Path\nPath('/workspace/executed').write_text('unwanted')\n", True)

    async def test_bound_validation_hash_conflict_publication_and_durable_receipt(self):
        f = self.fixture
        invalid = await self.call('validate_skill'); self.assertFalse(invalid['success'])
        self.assertTrue(any('SKILL.md' in message for message in invalid['skill']['errors']))
        self.draft(); checked = await self.call('validate_skill'); self.assertTrue(checked['success'], checked)
        self.assertFalse(checked['skill']['saved']); self.assertEqual(checked['skill']['activeRevision'], 0)
        old = {k: checked['skill'][k] for k in ('revision', 'draftHash')}
        self.draft('Changed after validation.\n')
        self.assertEqual((await self.call('save_skill', old))['error'], 'conflict')
        checked = await self.call('validate_skill'); body = {k: checked['skill'][k] for k in ('revision', 'draftHash')}
        saved = await self.call('save_skill', body, 'confirmed-save')
        self.assertTrue(saved['success'], saved); self.assertEqual(saved['skill']['activeRevision'], 1)
        self.assertEqual(saved['skill']['activeHash'], body['draftHash'])
        self.assertEqual(await self.call('save_skill', body, 'confirmed-save'), saved)
        self.assertEqual((await self.call('save_skill', {**body, 'draftHash': '0'*64}, 'confirmed-save'))['error'], 'conflict')
        self.assertFalse((self.worker.store.workspace / 'executed').exists())
        with closing(packages.connect(f.skills)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM saves').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 1)
        with self.assertRaises(packages.SkillFault):
            with packages.locked(f.skills, f.ids[0]): self.fail('Helper released the worker workspace lease')
        self.assertEqual(set(tools_for(SKILL_PROFILE)), set(LEGACY_TOOLS))
        self.assertEqual(len(tools_for(AUTHOR_PROFILE)), 11)

    async def test_unknown_save_is_not_replayed_and_stops_following_effects(self):
        self.draft(); checked = await self.call('validate_skill'); body = {k: checked['skill'][k] for k in ('revision', 'draftHash')}
        saved = await self.call('save_skill', body, 'lost-save-result'); self.assertTrue(saved['success'])
        with self.worker.store.db:
            self.worker.store.db.execute("UPDATE tools SET result=NULL,state='unknown' WHERE call_id='lost-save-result'")
        self.worker.skills.call = AsyncMock()
        unknown = await self.call('save_skill', body, 'lost-save-result')
        self.assertEqual(unknown['error'], 'unknown'); self.worker.skills.call.assert_not_called()
        denied = await self.call('write_file', {'path': 'another.txt', 'content': 'must not run', 'expectedSha256': None})
        self.assertEqual(denied['error'], 'interrupted')
        with closing(packages.connect(self.fixture.skills)) as db:
            self.assertEqual(db.execute('SELECT active_revision FROM skills WHERE id=?', (self.fixture.ids[0],)).fetchone()[0], 1)

    async def test_permissions_busy_terminals_owner_lease_and_stop_reject_before_effect(self):
        self.draft(); worker = self.worker
        worker.config['permissions']['studio.save_skill'] = False
        worker.skills.call = AsyncMock()
        denied = await self.call('save_skill', {'revision': 1, 'draftHash': '0'*64})
        self.assertEqual(denied['error'], 'disabled'); worker.skills.call.assert_not_called()
        from skill_tools import SkillTools
        worker.skills = SkillTools(worker)
        worker.terminals.processes['live'] = SimpleNamespace(finished=asyncio.Event())
        try: self.assertEqual((await self.call('validate_skill'))['error'], 'busy')
        finally: worker.terminals.processes.clear()
        original = worker.lease; worker.lease = open_lock(self.fixture.projects, 'skill', self.fixture.ids[1])
        try: self.assertEqual((await self.call('validate_skill'))['error'], 'denied')
        finally: worker.lease.close(); worker.lease = original
        transition(worker.store, worker.run_id, 'stopping')
        self.assertEqual((await self.call('validate_skill'))['error'], 'interrupted')
        self.assertEqual((await self.call('save_skill', {'revision': 1, 'draftHash': '0'*64}))['error'], 'interrupted')

    async def test_legacy_author_thread_keeps_its_original_tool_profile(self):
        f = self.fixture
        transition(self.worker.store, self.run['id'], 'completed')
        self.worker.lease.close(); self.worker.lease = None
        with f.open() as store:
            settings = json.loads(store.row(f.session['id'])['settings'])
            settings['permissions'] = {'studio.'+name: True for name in LEGACY_TOOLS}
            with store.db:
                store.db.execute('UPDATE sessions SET settings=?,engine=?,thread_id=? WHERE id=?',
                    (encode(settings), encode({**f.engine, 'profile': SKILL_PROFILE}), 'existing-author-v1-thread', f.session['id']))
            restored = store.get(f.session['id'])
            self.assertEqual(restored['engine']['profile'], SKILL_PROFILE)
            self.assertEqual(store.row(f.session['id'])['thread_id'], 'existing-author-v1-thread')
            self.assertEqual(len(restored['permissions']), 9)


if __name__ == '__main__': unittest.main()
