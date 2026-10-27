"""Real active-run broker and file namespace, without compiler/VM/model execution."""
import asyncio
import hashlib
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import test_roadmap_tools as fixtures
from profile import CODEX_SHA256
from run_store import transition


class CleanupToolsTest(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.RoadmapToolsTest.setUp
    tearDown = fixtures.RoadmapToolsTest.tearDown
    open = fixtures.RoadmapToolsTest.open
    start = fixtures.RoadmapToolsTest.start
    finish = fixtures.RoadmapToolsTest.finish
    call = fixtures.RoadmapToolsTest.call
    good = fixtures.RoadmapToolsTest.good

    def files(self, worker):
        # Only the SDK context is an empty fixture. File operations themselves
        # run through the real fixed file worker and networkless bwrap namespace.
        cache = self.root / 'OwnFileCache'; (cache / 'global/p').mkdir(parents=True)
        worker.sandbox.context = {'paths': {}, 'cache': cache}
        worker.sandbox.cache = cache / 'Run'; (worker.sandbox.cache / 'home').mkdir(parents=True)
        worker.sandbox.binary = Path(__file__).resolve().parents[2] / 'Data/R4OS/Toolchains/Codex/0.163.0/codex'
        self.assertEqual(hashlib.sha256(worker.sandbox.binary.read_bytes()).hexdigest(), CODEX_SHA256)

    async def initialize(self, worker):
        return await self.good(worker, 'update_roadmap', {'operation': 'initialize', 'requestId': str(uuid.uuid4())})

    def prepare(self, initial):
        return {'action': 'prepare', 'requestId': str(uuid.uuid4()), 'versionId': initial['currentVersionId'],
                'currentVersionId': initial['currentVersionId'], 'expectedRevision': initial['revision'], 'cleanupRequested': True}

    async def test_real_cleanup_then_permitted_file_write_and_document_receipt_preserve_version(self):
        self.data['text'] = 'Bitte Roadmap aufräumen.'
        worker = self.start(); await asyncio.to_thread(self.files, worker)
        result = await self.call(worker, 'create_directory', {'path': 'Docs'}); self.assertTrue(result['success'], result)
        created = await self.call(worker, 'write_file', {'path': 'Docs/Decision.md', 'content': 'Existing user decision\n', 'expectedSha256': None})
        self.assertTrue(created['success'], created)
        initial = await self.initialize(worker); arguments = self.prepare(initial)
        prepared = await self.good(worker, 'cleanup_roadmap', arguments)
        self.assertEqual(prepared['phase'], 'archive_ready')
        archive = worker.store.workspace / 'Docs/Changelogs/0.1.X.txt'
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), prepared['archive']['sha256'])
        updated = await self.call(worker, 'write_file', {'path': 'Docs/Decision.md', 'content': 'Existing user decision\nReviewed and preserved during cleanup\n', 'expectedSha256': created['sha256']})
        self.assertTrue(updated['success'], updated)
        read = await self.call(worker, 'read_file', {'path': 'Docs/Decision.md'})
        self.assertTrue(read['success']); self.assertEqual(read['sha256'], updated['sha256'])
        checkpoint = {**arguments, 'requestId': str(uuid.uuid4()), 'workflowId': prepared['workflowId'],
                      'documents': [{'path': 'Docs/Decision.md', 'expectedSha256': created['sha256'], 'sha256': read['sha256']}],
                      'documentationSummary': 'Reviewed the complete archive and preserved the existing durable decision with its explicit readback hash.'}
        verified = await self.good(worker, 'cleanup_roadmap', checkpoint)
        self.assertEqual(verified['phase'], 'documents_verified')
        self.assertEqual(await self.good(worker, 'cleanup_roadmap', checkpoint), verified)
        outside = await self.call(worker, 'read_file', {'path': '../Roadmap/Roadmap.sqlite'})
        self.assertFalse(outside['success'])
        current = await self.good(worker, 'read_roadmap', {'view': 'current'})
        self.assertEqual(current['entity']['status'], 'open')
        self.assertEqual(len((await self.good(worker, 'read_roadmap', {'view': 'versions'}))['items']), 1)
        self.finish(worker)
        self.data['text'] = 'Continue the original cleanup without repeating file writes.'
        later = self.start()
        status = await self.good(later, 'cleanup_roadmap', {'action': 'status', 'workflowId': prepared['workflowId']})
        self.assertEqual(status['phase'], 'documents_verified'); self.assertEqual(status['documentCount'], 1)

    async def test_actual_user_context_and_frozen_file_rights_gate_before_archive(self):
        self.data['text'] = 'Roadmap abarbeiten.'
        worker = self.start(); initial = await self.initialize(worker)
        denied = await self.call(worker, 'cleanup_roadmap', self.prepare(initial))
        self.assertEqual(denied['error'], 'denied'); self.assertFalse((worker.store.workspace / 'Docs').exists())
        self.finish(worker)
        with self.open() as store:
            session = store.get(self.sid)
            store.update(self.sid, {'revision': session['revision'], 'permissions': {**session['permissions'], 'studio.write_file': False}}, self.providers)
        self.data['text'] = 'Please clean up the roadmap.'
        worker = self.start()
        denied = await self.call(worker, 'cleanup_roadmap', self.prepare(initial))
        self.assertEqual(denied['error'], 'denied'); self.assertFalse((worker.store.workspace / 'Docs').exists())

    async def test_lost_prepare_reply_reconciles_original_archive_from_new_run(self):
        self.data['text'] = 'Tidy up the roadmap.'
        worker = self.start(); initial = await self.initialize(worker); arguments = self.prepare(initial)
        original_spawn = asyncio.create_subprocess_exec
        async def lose(*args, **kwargs):
            process = await original_spawn(*args, **kwargs); communicate = process.communicate
            async def lost(*args, **kwargs):
                raw, _ = await communicate(*args, **kwargs); self.assertIn(b'archive_ready', raw)
                raise ConnectionError('Own lost cleanup result')
            process.communicate = lost
            return process
        worker.development.stop_owned = AsyncMock()
        with patch('roadmap_tools.asyncio.create_subprocess_exec', side_effect=lose):
            result = await self.call(worker, 'cleanup_roadmap', arguments)
        self.assertEqual(result['error'], 'unknown'); await asyncio.sleep(0)
        archive = worker.store.workspace / 'Docs/Changelogs/0.1.X.txt'; before = (archive.stat().st_ino, archive.read_bytes())
        transition(worker.store, worker.run_id, 'unknown'); worker.lease.close()
        self.data['text'] = 'Resume the original workflow.'
        later = self.start()
        status = await self.good(later, 'cleanup_roadmap', {'action': 'status', 'workflowId': arguments['requestId']})
        self.assertEqual(status['phase'], 'archive_ready')
        recovered = await self.good(later, 'cleanup_roadmap', arguments)
        self.assertEqual(recovered['workflowId'], status['workflowId'])
        self.assertEqual(recovered['archive'], status['archive'])
        self.assertEqual(recovered['phase'], 'archive_ready')
        self.assertEqual((archive.stat().st_ino, archive.read_bytes()), before)
