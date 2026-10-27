"""Filesystem boundaries for the private catalog; no network or actual logins."""
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from catalog import operation, CatalogFault


class StorageBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.directory = self.root / 'RemoteHosts'
        self.create = {'operation': 'create', 'input': {'requestId': str(uuid.uuid4()), 'name': 'Straße', 'address': '127.0.0.1'}}

    def test_symlinked_ancestor_directory_database_and_hardlink_preserve_foreign_bytes(self):
        outside = self.root / 'Outside'; outside.mkdir(); link = self.root / 'Linked'; link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(CatalogFault): operation(link / 'RemoteHosts', self.create)
        self.assertEqual(list(outside.iterdir()), [])
        self.directory.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(CatalogFault): operation(self.directory, self.create)
        self.assertEqual(list(outside.iterdir()), []); self.directory.unlink(); self.directory.mkdir(mode=0o700)
        foreign = outside / 'keep'; foreign.write_text('Foreign bytes must survive')
        target = self.directory / 'RemoteHosts.sqlite'; target.symlink_to(foreign)
        with self.assertRaises(CatalogFault): operation(self.directory, self.create)
        self.assertEqual(foreign.read_text(), 'Foreign bytes must survive'); target.unlink(); foreign.chmod(0o600); os.link(foreign, target)
        with self.assertRaises(CatalogFault): operation(self.directory, self.create)
        self.assertEqual(foreign.read_text(), 'Foreign bytes must survive')
