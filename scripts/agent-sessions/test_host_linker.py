"""Only temporary public-tool fixtures; no host alternatives are modified."""
import os
from pathlib import Path
import tempfile
import unittest

from host_linker import qualify, bindings


class HostLinker(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name); self.public = root / 'usr'; self.bin = self.public / 'bin'; self.bin.mkdir(parents=True)
        self.entry = self.bin / 'cc'; self.alt = root / 'etc/alternatives/cc'; self.alt.parent.mkdir(parents=True)
        self.driver = self.bin / 'driver'; self.driver.write_text('fixture executable'); self.driver.chmod(0o755)
    def selection(self): return qualify(self.entry,self.alt,self.public)

    def test_original_alternative_and_relative_public_chain(self):
        self.entry.symlink_to(self.alt); self.alt.symlink_to(self.bin / 'gcc'); (self.bin / 'gcc').symlink_to('driver')
        value = self.selection(); self.assertTrue(value['available']); self.assertEqual(value['target'],str(self.driver))
        args = bindings(value); self.assertIn(str(self.driver),args)
        self.assertNotIn(str(self.alt.parent),args); self.assertNotIn(str(self.alt),args)
        self.assertEqual(args.count('--ro-bind'),1); self.assertIn('/etc/alternatives/cc',args)
        self.assertEqual(os.readlink(self.alt),str(self.bin/'gcc'))

    def test_missing_loop_nonexecutable_and_foreign_targets_are_unavailable(self):
        self.assertEqual(self.selection()['code'],'missing')
        self.entry.symlink_to(self.alt); self.alt.symlink_to(self.entry)
        self.assertEqual(self.selection()['code'],'cycle')
        self.alt.unlink(); self.alt.symlink_to(self.driver); self.driver.chmod(0o600)
        self.assertEqual(self.selection()['code'],'non_executable')
        self.driver.chmod(0o755); foreign=self.public.parent/'private-driver'; foreign.write_text('private'); foreign.chmod(0o755)
        self.alt.unlink(); self.alt.symlink_to(foreign)
        value=self.selection(); self.assertFalse(value['available']); self.assertNotIn(str(foreign),bindings(value))
        self.assertEqual(value['code'],'outside_public_tools')
        self.assertIn('Host C linker unavailable',value['reason'])

    def test_only_cc_alternative_is_allowed_and_parent_symlinks_are_rejected(self):
        other=self.alt.with_name('other'); other.symlink_to(self.driver); self.entry.symlink_to(other)
        self.assertFalse(self.selection()['available']); self.entry.unlink()
        outside=self.public.parent/'private'; outside.mkdir(); (outside/'driver').write_text('private')
        (outside/'driver').chmod(0o755); (self.bin/'nested').symlink_to(outside)
        self.entry.symlink_to(self.bin/'nested/driver'); self.assertFalse(self.selection()['available'])
        self.entry.unlink(); self.entry.symlink_to(self.driver); self.assertTrue(self.selection()['available'])


if __name__ == '__main__': unittest.main()
