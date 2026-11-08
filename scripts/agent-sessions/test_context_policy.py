"""Context settings preserve saved values, original receipts and run snapshots."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid

from context_policy import DEFAULT, freeze, read, receipt, threshold, update
from store import ProjectFault
from system_prompt import location


class ContextPolicy(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.projects = Path(self.temporary.name) / 'Projects'
        self.projects.mkdir()

    def save(self, **changes):
        return update(self.projects, {'requestId': str(uuid.uuid4()), 'revision': read(self.projects)['revision'],
            'action': 'save', 'budgetTokens': 123456, 'enabled': True, **changes})

    def test_legacy_read_migration_and_original_receipt(self):
        path = location(self.projects, create=True)
        with sqlite3.connect(path) as db:
            db.executescript('PRAGMA user_version=1; CREATE TABLE system_prompt(id INTEGER PRIMARY KEY,prompt TEXT,revision INTEGER);'
                'CREATE TABLE global_context(id INTEGER PRIMARY KEY,revision INTEGER,budget_tokens INTEGER);'
                'INSERT INTO global_context VALUES(1,7,345678);')
        original = path.read_bytes()
        self.assertEqual(read(self.projects)['budgetTokens'], 345678)
        self.assertTrue(read(self.projects)['enabled'])
        self.assertEqual(path.read_bytes(), original)
        data = {'requestId': str(uuid.uuid4()), 'revision': 7, 'action': 'save', 'budgetTokens': 345678, 'enabled': False}
        result = update(self.projects, data)
        self.assertEqual(result['revision'], 8)
        self.assertFalse(result['enabled'])
        self.assertEqual(update(self.projects, data), result)
        self.assertEqual(receipt(self.projects, data['requestId']), result)
        with self.assertRaises(ProjectFault): update(self.projects, {**data, 'enabled': True})
        with self.assertRaises(ProjectFault): self.save(revision=7)
        self.assertEqual(read(self.projects)['budgetTokens'], 345678)
        # An old client changes only the number, never silently re-enables it.
        legacy = {k:v for k,v in {**data, 'requestId':str(uuid.uuid4()), 'revision':8, 'budgetTokens':456789}.items() if k!='enabled'}
        self.assertFalse(update(self.projects, legacy)['enabled'])

    def test_reset_validation_and_frozen_next_run(self):
        self.assertEqual(read(self.projects)['budgetTokens'], DEFAULT)
        first = self.save()
        config = {'engine': {'kind': 'studio'}}
        freeze(config, self.projects, None)
        self.save(enabled=False)
        self.assertTrue(config['contextPolicy']['enabled'])
        restored = {'engine': {'kind': 'studio'}}
        freeze(restored, self.projects, config)
        self.assertEqual(restored, config)
        next_run = {'engine': {'kind': 'studio'}}
        freeze(next_run, self.projects, None)
        self.assertIsNone(threshold(next_run, None))
        self.assertEqual(threshold(next_run, 10000), 8000)
        self.assertEqual(threshold(config, 1000000), first['budgetTokens'])
        reset = update(self.projects, {'requestId':str(uuid.uuid4()), 'revision':read(self.projects)['revision'], 'action':'reset'})
        self.assertTrue(reset['enabled']); self.assertEqual(reset['budgetTokens'], DEFAULT)
        for changes in ({'enabled':1}, {'budgetTokens':True}, {'budgetTokens':0}, {'budgetTokens':10000001}):
            with self.subTest(changes=changes), self.assertRaises(ProjectFault): self.save(**changes)


if __name__ == '__main__': unittest.main()
