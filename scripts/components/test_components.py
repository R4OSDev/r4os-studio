"""The SDK-only component boundary; retired independent loaders have no tests."""
from pathlib import Path
import tempfile
import unittest

from common import safe_url
from service import Manager


class ComponentTests(unittest.TestCase):
    def test_sdk_owned_components_cannot_be_selected_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = Manager(Path(temporary))
            self.assertEqual(manager.state['defaults'], {})
            for kind in ('contract', 'libraries', 'zig', 'rust'):
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    manager.set_default(kind, 'unavailable')
            self.assertEqual(manager.state['defaults'], {})

    def test_source_urls_reject_credentials_untrusted_hosts_and_local_network(self):
        for value in ('http://github.com/x', 'https://github.com.evil.test/x', 'https://127.0.0.1/',
                      'https://user:password@github.com/x', 'file:///etc/passwd', 'https://github.com:8080/x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_url(value)
        self.assertEqual(safe_url('https://codeload.github.com/R4OSDev/r4os-sdk/tar.gz/' + 'a' * 40),
                         'https://codeload.github.com/R4OSDev/r4os-sdk/tar.gz/' + 'a' * 40)


if __name__ == '__main__': unittest.main()
