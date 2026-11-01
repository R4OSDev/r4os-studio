"""Pin publication, admission and original-request recovery without user data."""
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from store import connect, ProjectFault
from git_metadata import portable
import project_pins as pins
from project_use import acquire


class PinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.projects = Path(self.temp.name) / 'Projects'; self.root = Path(self.temp.name) / 'R4OS'
        self.id = str(uuid.uuid4()); self.request = str(uuid.uuid4())
        self.old = {'sdk': {'version': '0.64.92', 'revision': '1' * 40}, 'contract': {}, 'zig': {}}
        self.new = {'sdk': {'version': '0.64.127', 'revision': '2' * 40}, 'contract': {}, 'zig': {}, 'sdkTools': {'releaseSha256':'f' * 64}}
        with closing(connect(self.projects)) as db, db:
            db.execute("INSERT INTO projects VALUES (?,?, '', 'Zig','terminal','APP',NULL,?,'before','before',1,'ready')", (self.id, 'Own QA', json.dumps(self.old)))
        self.work = self.projects / self.id / 'Workspace'; (self.work / '.r4os-studio').mkdir(parents=True)
        self.meta = self.work / '.r4os-studio/project.json'
        self.meta.write_text(json.dumps({**portable(pins.project(self.projects, self.id)), 'custom': 'preserve'}))
        (self.work / 'module.R4MF').write_text('Original manifest\n')
        (self.work / 'main.zig').write_text('Original source\n')
        self.input = {'requestId': self.request, 'revision': 1, 'sdkId': '2' * 40, 'selectionId': 'a' * 64}
        self.hosts = {'agents': True, 'development': True, 'unsafe': False}
        self.choice = {'sdkId': '2' * 40, 'available': True, 'selectionId': 'a' * 64, 'components': self.new, 'releaseSha256': 'f' * 64}
        for target, result in [('project_pins.choices', [self.choice]), ('sdk.profile', {'pins': self.new}),
                               ('github_import.manifest', 'APP'), ('clear_cache.worker_admission', None)]:
            mock = patch(target, return_value=result); mock.start(); self.addCleanup(mock.stop)

    def apply(self, data=None): return pins.apply(self.projects, self.root, self.id, data or self.input, self.hosts)

    def assert_pair(self, expected, revision):
        current = pins.project(self.projects, self.id)
        self.assertEqual(current['pins'], expected); self.assertEqual(current['revision'], revision)
        self.assertEqual(json.loads(self.meta.read_text())['pins'], expected)
        self.assertEqual(json.loads(self.meta.read_text())['custom'], 'preserve')
        self.assertEqual((self.work / 'main.zig').read_text(), 'Original source\n')
        self.assertEqual((self.work / 'module.R4MF').read_text(), 'Original manifest\n')

    def test_apply_original_receipt_and_conflicting_id(self):
        result = self.apply(); self.assertEqual(result['state'], 'complete'); self.assert_pair(self.new, 2)
        self.assertEqual(self.apply(), result)
        self.assertEqual(pins.receipt(self.projects, self.id, self.request), {**result, 'input': self.input})
        with self.assertRaises(ProjectFault): self.apply({**self.input, 'sdkId': '3' * 40})
        self.assert_pair(self.new, 2)

    def test_revision_selection_and_native_manifest_rejections_preserve_sources(self):
        for value in ({**self.input, 'revision': 2}, {**self.input, 'selectionId': 'b' * 64}):
            with self.assertRaises(ProjectFault): self.apply(value)
        with patch('github_import.manifest', side_effect=ProjectFault('SDK rejected manifest')):
            with self.assertRaises(ProjectFault): self.apply()
        self.assert_pair(self.old, 1)
        self.assertEqual(pins.receipt(self.projects, self.id, self.request)['state'], 'missing')

    def test_active_project_and_remote_unknown_block_before_validation(self):
        with acquire(self.projects, self.id):
            with self.assertRaises(ProjectFault): self.apply()
        with patch('project_pins.require_idle', side_effect=ProjectFault('Active job')):
            with self.assertRaises(ProjectFault): self.apply()
        with patch('remote_binding.assert_change_safe', side_effect=ProjectFault('Unknown remote job')):
            with self.assertRaises(ProjectFault): self.apply()
        self.assert_pair(self.old, 1)

    def test_selected_release_cannot_change_during_verification(self):
        changed = {**self.new, 'sdkTools': {'releaseSha256': 'e' * 64}}
        with patch('sdk.profile', return_value={'pins': changed}):
            with self.assertRaisesRegex(ProjectFault, 'release metadata changed'): self.apply()
        changed = {**self.new, 'sdk': {**self.new['sdk'], 'version': 'other'}}
        with patch('sdk.profile', return_value={'pins': changed}):
            with self.assertRaisesRegex(ProjectFault, 'component metadata changed'): self.apply()
        self.assert_pair(self.old, 1)

    def test_file_published_before_database_commit_is_recoverable(self):
        replace = os.replace
        def interrupted(source, destination):
            replace(source, destination)
            if destination == self.meta: raise OSError('Process ended after rename')
        with patch('project_pins.os.replace', side_effect=interrupted):
            with self.assertRaises(OSError): self.apply()
        self.assertEqual(pins.project(self.projects, self.id)['pins'], self.old)
        self.assertEqual(json.loads(self.meta.read_text())['pins'], self.new)
        for exclusive in (False, True):
            with self.assertRaises(ProjectFault): acquire(self.projects, self.id, exclusive=exclusive)
        self.assertEqual(pins.receipt(self.projects, self.id, self.request)['state'], 'unknown')
        self.apply(); self.assert_pair(self.new, 2)
        with acquire(self.projects, self.id): pass

    def test_database_committed_before_final_receipt_recovers_without_second_update(self):
        save = pins.save
        def interrupted(path, value):
            if value.get('result'): raise OSError('Process ended before final receipt')
            return save(path, value)
        with patch('project_pins.save', side_effect=interrupted):
            with self.assertRaises(OSError): self.apply()
        self.assert_pair(self.new, 2)
        with self.assertRaises(ProjectFault): self.apply({**self.input, 'requestId': str(uuid.uuid4())})
        self.apply(); self.assert_pair(self.new, 2)

    def test_metadata_conflict_and_symlink_are_preserved(self):
        raw = self.meta.read_text(); value = json.loads(raw); value['pins']['sdk']['version'] = 'changed'
        self.meta.write_text(json.dumps(value))
        with self.assertRaises(ProjectFault): self.apply()
        self.assertEqual(json.loads(self.meta.read_text()), value)
        outside = Path(self.temp.name) / 'outside'; outside.write_text(raw)
        self.meta.unlink(); self.meta.symlink_to(outside)
        with self.assertRaises(OSError): self.apply()
        self.assertTrue(self.meta.is_symlink()); self.assertEqual(outside.read_text(), raw)

    def test_recovery_does_not_overwrite_external_change(self):
        with patch('project_pins.publish', side_effect=OSError('Interrupted')):
            with self.assertRaises(OSError): self.apply()
        self.meta.write_text('external change')
        with self.assertRaises(ProjectFault): self.apply()
        self.assertEqual(self.meta.read_text(), 'external change')
        self.assertTrue(pins.gate_path(self.projects, self.id).exists())


if __name__ == '__main__': unittest.main()
