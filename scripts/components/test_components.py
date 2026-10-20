"""Focused checks for profile atomicity and the component service trust boundary."""
import json
from pathlib import Path
import tempfile
import unittest

from common import safe_url
from service import Manager, atomic


class ComponentTests(unittest.TestCase):
    def test_defaults_require_local_versions_and_preserve_profile_after_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'Toolchains/Zig/0.16.0'
            path.mkdir(parents=True)
            (path / 'zig').write_text('compiler fixture')
            atomic(path / '.studio-component.json', {'version': '0.16.0', 'sha256': 'a' * 64})
            manager = Manager(root)
            before = manager.profile.read_bytes()
            with self.assertRaises(ValueError):
                manager.set_default('zig', '../../outside')
            with self.assertRaises(ValueError):
                manager.set_default('zig', 'not-installed')
            self.assertEqual(manager.profile.read_bytes(), before)
            manager.set_default('zig', '0.16.0')
            self.assertEqual(Manager(root).status()['components']['zig']['activeId'], '0.16.0')
            self.assertEqual(json.loads(manager.profile.read_text())['defaults']['zig']['binary'], str(path / 'zig'))

    def test_source_urls_reject_credentials_untrusted_hosts_and_local_network(self):
        for value in ('http://github.com/x', 'https://github.com.evil.test/x', 'https://127.0.0.1/',
                      'https://user:password@github.com/x', 'file:///etc/passwd', 'https://github.com:8080/x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_url(value)
        self.assertEqual(safe_url('https://codeload.github.com/R4OSDev/r4os-sdk/tar.gz/' + 'a' * 40),
                         'https://codeload.github.com/R4OSDev/r4os-sdk/tar.gz/' + 'a' * 40)


if __name__ == '__main__':
    unittest.main()
