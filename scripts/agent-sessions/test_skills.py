"""Owner isolation, shared admission, native continuity and real author namespace."""
import asyncio
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from host import Host
from profile import SKILL_PROFILE, CODEX_VERSION, CODEX_SHA256, LEGACY_TOOLS
from run_store import admit, get_run, transition
from session_store import SessionStore, encode
from store import ProjectFault
from tool_catalog import specifications, validate_arguments
from worker import Worker

spec = importlib.util.spec_from_file_location('skill_package_store', Path(__file__).resolve().parents[1] / 'skills/store.py')
packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)


class Skills(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.projects = self.root / 'Projects'; self.skills = self.root / 'Skills'; self.r4os = self.root / 'R4OS'
        self.providers = self.root / 'LLMProvider'; self.provider = str(uuid.uuid4())
        self.ids = [str(uuid.uuid4()) for _ in range(2)]
        with closing(packages.connect(self.skills)) as db:
            for ident in self.ids: packages.create(db, self.skills, {'id': ident, 'name': 'Fixture'})
        (self.providers / self.provider).mkdir(parents=True)
        (self.providers / 'providers.json').write_text(encode([{'id': self.provider, 'name': 'Fixture', 'type': 'openai', 'connected': True}]))
        (self.providers / self.provider / 'models_cache.json').write_text(encode({'models': [{'slug': 'fixture', 'visibility': 'list', 'supported_reasoning_levels': [{'effort': 'low'}]}]}))
        self.engine = {'profile': SKILL_PROFILE, 'version': CODEX_VERSION, 'sha256': CODEX_SHA256, 'available': True}
        with self.open() as store, patch('session_store.engine', return_value=self.engine):
            self.session = store.create(self.settings(), self.providers)
        self.config = {'projects': str(self.projects), 'providers': str(self.providers), 'r4os': str(self.r4os), 'uid': os.getuid(), 'maxActiveRuns': 2}

    def tearDown(self): self.temp.cleanup()
    def open(self, ident=None): return closing(SessionStore(self.projects, self.r4os, ident or self.ids[0], 'skill'))
    def settings(self): return {'name': 'Author', 'providerId': self.provider, 'model': 'fixture', 'effort': 'low', 'requestId': str(uuid.uuid4())}
    def input(self): return {'requestId': str(uuid.uuid4()), 'revision': self.session['revision'], 'text': 'Edit this skill draft.'}
    def admit(self):
        with self.open() as store: return admit(store, self.session['id'], self.input(), self.providers)[0]
    def manifest(self, run): return {**self.config, 'ownerType': 'skill', 'ownerId': self.ids[0], 'sessionId': self.session['id'], 'runId': run['id'], 'release': 'fixture', 'version': '0.4.5'}

    async def test_skill_ownership_permissions_receipts_and_manual_write_exclusion(self):
        self.assertEqual(self.session['owner'], {'type': 'skill', 'id': self.ids[0]})
        self.assertNotIn('projectId', self.session)
        self.assertFalse(self.projects.exists())
        self.assertEqual(set(self.session['permissions']), {'studio.' + name for name in LEGACY_TOOLS})
        self.assertEqual(len(specifications(SKILL_PROFILE)), 9)
        with self.assertRaises(ValueError): validate_arguments('read_file', {'path': '.', 'root': 'sdk'}, SKILL_PROFILE)
        with self.open(self.ids[1]) as store:
            with self.assertRaises(ProjectFault): store.get(self.session['id'])
        with self.open() as store:
            data = self.input(); run, fresh = admit(store, self.session['id'], data, self.providers)
            duplicate, again = admit(store, self.session['id'], data, self.providers)
            self.assertTrue(fresh); self.assertFalse(again); self.assertEqual(run, duplicate)
            snapshot = json.loads(get_run(store, run['id'])['config'])
            self.assertIn('skillManagerPrompt', snapshot)
            self.assertFalse(set(snapshot) & {'projectPins', 'systemPrompt', 'projectInstructions'})
            with self.assertRaises(ProjectFault): admit(store, self.session['id'], self.input(), self.providers)
            with self.assertRaises(ProjectFault): store.update(self.session['id'], {'revision': 1, 'name': 'Busy'}, self.providers)
            with self.assertRaises(packages.SkillFault):
                with packages.locked(self.skills, self.ids[0]): self.fail('Queued author run allowed manual editing')
            transition(store, run['id'], 'interrupted')
        with packages.locked(self.skills, self.ids[0]): pass
        with self.open() as store:
            self.assertEqual(store.history(self.session['id'])['items'][0]['text'], data['text'])

    async def test_shared_capacity_stop_binding_and_recovery_without_inference(self):
        host = Host(self.config); run = self.admit()
        host.refresh = AsyncMock()
        project_run = str(uuid.uuid4())
        host.active = {project_run: {'projectId': str(uuid.uuid4())}, run['id']: self.manifest(run)}
        request = {'operation': 'start_run', 'ownerType': 'skill', 'ownerId': self.ids[0], 'sessionId': self.session['id'], 'input': self.input()}
        with self.assertRaisesRegex(ProjectFault, 'maximum number'): await host.handle(request)
        with self.open() as store:
            row = get_run(store, run['id']); original = json.loads(store.db.execute('SELECT payload FROM items WHERE run_id=?', (run['id'],)).fetchone()[0])
            request['input'] = {'requestId': row['request_id'], 'revision': 1, 'text': original['text']}
        self.assertEqual((await host.handle(request))['id'], run['id'])
        control = AsyncMock(return_value='')
        with patch('host.systemctl', control):
            with self.assertRaises(ProjectFault): await host.stop(self.ids[1], self.session['id'], run['id'], 'skill')
            await host.stop(self.ids[0], self.session['id'], run['id'], 'skill')
        self.assertEqual([c.args[0] for c in control.call_args_list], ['stop'])
        queued = self.admit(); recovered = Host(self.config)
        with patch('host.systemctl', AsyncMock(return_value='')) as control:
            await recovered.recover()
            self.assertFalse(any(c.args[0] in ('start', 'stop') for c in control.call_args_list))
        with self.open() as store: self.assertEqual(get_run(store, queued['id'])['state'], 'unknown')

    async def test_native_thread_is_resumed_and_failed_resume_is_preserved(self):
        from system_prompt import update as update_prompt, read as read_prompt
        update_prompt(self.projects, {'revision': 0, 'text': 'Skill author prompt A'}, kind='skill')
        project_prompt = read_prompt(self.projects)
        seen = []; fail_resume = False
        class Native:
            def __init__(self, args, notify, tool): self.notify = notify
            async def start(self): pass
            async def close(self): pass
            async def request(self, method, params, **kwargs):
                seen.append((method, params))
                if method == 'thread/resume' and fail_resume: raise RuntimeError('Corrupt native history')
                if method.startswith('thread/'): return {'thread': {'id': 'same-native-author-thread'}}
                if method == 'turn/start':
                    await self.notify('turn/completed', {'threadId': 'same-native-author-thread', 'turn': {'id': 'turn', 'status': 'completed'}})
                    return {'turn': {'id': 'turn'}}
                return {}
        for index in range(2):
            run = self.admit()
            if index == 0: update_prompt(self.projects, {'revision': 1, 'text': 'Skill author prompt B'}, kind='skill')
            worker = Worker(self.manifest(run))
            with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', Native): await worker.run()
            with self.open() as store: self.assertEqual(get_run(store, run['id'])['state'], 'completed')
        self.assertEqual(sum(method == 'thread/start' for method, _ in seen), 1)
        self.assertEqual(sum(method == 'thread/resume' for method, _ in seen), 1)
        self.assertEqual([p['threadId'] for method, p in seen if method == 'thread/resume'], ['same-native-author-thread'])
        self.assertTrue(all('Skill Manager instructions' in p['baseInstructions'] for method, p in seen if method.startswith('thread/')))
        instructions = [p['baseInstructions'] for method, p in seen if method.startswith('thread/')]
        self.assertTrue(instructions[0].endswith('Skill author prompt A'))
        self.assertTrue(instructions[1].endswith('Skill author prompt B'))
        self.assertEqual(read_prompt(self.projects), project_prompt)
        fail_resume = True; run = self.admit(); worker = Worker(self.manifest(run))
        with patch('worker.prepare', return_value=([], {})), patch('worker.CodexRPC', Native): await worker.run()
        with self.open() as store:
            self.assertEqual(store.row(self.session['id'])['thread_id'], 'same-native-author-thread')
            self.assertEqual(get_run(store, run['id'])['state'], 'failed')
        self.assertEqual(sum(method == 'thread/start' for method, _ in seen), 1)
        self.assertEqual(sum(method == 'turn/start' for method, _ in seen), 2)

    @unittest.skipIf(os.getuid() == 0, 'Run actual author namespace as the unprivileged service user.')
    async def test_real_namespace_has_no_sdk_other_owners_or_credentials(self):
        installed = Path(__file__).resolve().parents[2] / 'Data/R4OS'
        if not (installed / 'Toolchains/Codex' / CODEX_VERSION / 'codex').is_file(): self.skipTest('Qualified Codex runtime absent')
        run = self.admit(); worker = Worker({**self.manifest(run), 'r4os': str(installed)})
        try:
            self.assertTrue((await worker.sandbox.file('create_directory', {'path': 'references'}))['success'])
            result = await worker.sandbox.file('write_file', {'path': 'references/probe.txt', 'content': 'only selected skill', 'expectedSha256': None})
            self.assertTrue(result['success'], result)
            denied = await worker.sandbox.file('read_file', {'path': '.', 'root': 'sdk'})
            self.assertFalse(denied['success'])
            command = '''python3 - <<'PY'
from pathlib import Path
import socket
assert Path('/workspace/references/probe.txt').read_text() == 'only selected skill'
for path in ['/codex','/session','/sdk','/contract','/zig','/rust','/Data','/root','/run/r4os-studio-vms','/workspace/../Sessions']:
 assert not Path(path).exists(), path
assert not Path('/workspace/module.R4MF').exists()
try: socket.create_connection(('1.1.1.1',443),timeout=.1)
except OSError: pass
else: raise AssertionError('Network unexpectedly available')
print('AUTHOR_NAMESPACE_OK')
PY'''
            result = await worker.terminals.call('exec_command', {'cmd': command, 'yield_time_ms': 1000})
            output = result['output']
            while result['state'] == 'running':
                result = await worker.terminals.call('write_stdin', {'processId': result['processId'], 'yield_time_ms': 1000}); output += result['output']
            self.assertEqual(result['exitCode'], 0, output); self.assertIn('AUTHOR_NAMESPACE_OK', output)
        finally: await worker.cleanup(); worker.store.close()


if __name__ == '__main__': unittest.main()
