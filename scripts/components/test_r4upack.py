"""Packer selection cannot change project defaults or admit altered executables."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from service import Manager, atomic
from r4upack import SPEC, SPEC_HASH, choose, inventory, pin, verify, install

class Packer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.manager = Manager(self.root)
        self.defaults = (self.root / 'Profiles/versions.json').read_bytes()

    def tearDown(self): self.tmp.cleanup()

    def fixture(self):
        source = Path(__file__).resolve().parents[2] / 'Data/R4OS/Toolchains/R4UPack' / SPEC['id']
        if not source.exists(): self.skipTest('Qualified local packer absent')
        target = self.root / 'Toolchains/R4UPack' / SPEC['id']
        shutil.copytree(source, target); return target

    def test_installation_inventory_requires_explicit_selection_and_does_not_change_sdk_pins(self):
        self.fixture()
        self.assertEqual(self.manager.status()['components']['r4upack']['activeId'], None)
        with self.assertRaisesRegex(ValueError, 'Select a qualified'): pin(self.root)
        self.manager.set_default('r4upack', SPEC['id'])
        selected = pin(self.root)
        self.assertEqual(selected['sha256'], SPEC['binarySha256'])
        self.assertEqual(selected['profileSha256'], SPEC_HASH)
        self.assertEqual((self.root / 'Profiles/versions.json').read_bytes(), self.defaults)
        with self.assertRaises(ValueError): choose(self.root, '/bin/sh', inventory(self.root))

    def test_altered_binary_or_retained_source_is_unavailable_and_not_overwritten(self):
        target = self.fixture(); self.manager.set_default('r4upack', SPEC['id'])
        binary = target / 'r4upack'; binary.write_bytes(b'changed binary')
        self.assertEqual(inventory(self.root), [])
        status = self.manager.status()['components']['r4upack']
        self.assertIn('missing or changed', status['error']); self.assertIsNone(status['activeId'])
        with self.assertRaisesRegex(ValueError, 'binary SHA-256'): install(self.manager)
        self.assertEqual(binary.read_bytes(), b'changed binary')
        self.assertEqual((self.root / 'Profiles/versions.json').read_bytes(), self.defaults)

    def test_symlinks_and_external_hash_path_bindings_are_rejected(self):
        target = self.fixture(); binary = target / 'r4upack'
        saved = target / 'saved'; binary.rename(saved); binary.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, 'unlinked regular'): verify(target)
        binary.unlink(); saved.rename(binary)
        external = {'directory': str(target), 'binary': str(binary), 'sha256': SPEC['binarySha256']}
        values = inventory(self.root, external)
        self.assertEqual(len(values), 2); self.assertTrue(values[1]['external'])
        with self.assertRaises(ValueError): inventory(self.root, {**external, 'sha256': '0' * 64})
        with self.assertRaises(ValueError): inventory(self.root, {**external, 'binary': '/usr/bin/true'})
        (target / 'sources/r4os-sdk/r4os/r4u_artifact.zig').write_text('altered source')
        with self.assertRaisesRegex(ValueError, 'source or license'): verify(target)

    def test_unsupported_selection_and_failed_source_download_preserve_configuration(self):
        selection = self.root / 'Profiles/r4upack.json'
        atomic(selection, {'schema': 99, 'id': 'preserve me'})
        before = selection.read_bytes()
        self.assertIn('Unsupported', self.manager.status()['components']['r4upack']['error'])
        with self.assertRaises(ValueError): pin(self.root)
        self.assertEqual(selection.read_bytes(), before)
        source = Path(__file__).resolve().parents[2] / 'Data/R4OS/Toolchains/Zig/0.16.0/zig'
        if not source.exists(): self.skipTest('Qualified Zig absent')
        # Copy a compiler fixture only to reach the source verification boundary.
        destination = self.root / 'Toolchains/Zig/0.16.0/zig'; destination.parent.mkdir(parents=True)
        shutil.copyfile(source, destination); destination.chmod(0o700)
        self.manager.job = {}
        with patch('r4upack.read_url', return_value=b'altered upstream source'):
            with self.assertRaisesRegex(ValueError, 'source SHA-256'): install(self.manager)
        self.assertFalse((self.root / 'Toolchains/R4UPack' / SPEC['id']).exists())
        self.assertEqual(selection.read_bytes(), before)
        self.assertEqual((self.root / 'Profiles/versions.json').read_bytes(), self.defaults)

if __name__ == '__main__': unittest.main()
