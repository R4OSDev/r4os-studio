"""Additive native declarations: older conversations retain their exact v5 tool contract."""
import hashlib
import json
import unittest
import importlib.util
from pathlib import Path
from profile import GIT_PROFILE, default_enabled, tools_for
from tool_catalog import specifications, validate_arguments


class GitHubProfileTest(unittest.TestCase):
    def test_v6_push_is_default_off_and_v5_native_declarations_are_unchanged(self):
        self.assertEqual(GIT_PROFILE, 'studio-tools-v6'); self.assertFalse(default_enabled('push_project'))
        self.assertIn('push_project', tools_for(GIT_PROFILE))
        for old in ('studio-tools-v1', 'studio-tools-v2', 'studio-tools-v3', 'studio-tools-v4', 'studio-tools-v5', 'studio-skill-tools-v1', 'studio-skill-tools-v2'):
            self.assertNotIn('push_project', tools_for(old))
        original = json.dumps(specifications('studio-tools-v5'), sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(original).hexdigest(), 'b743584c868f47a745e7ae4f88e7664ad902c8838cb0409ffa80638fd031148e')
        for invalid in ({}, {'commitMessage': ''}, {'commitMessage': 'a', 'token': 'forbidden'}, {'commitMessage': 'a' * 4001}):
            with self.assertRaises(ValueError): validate_arguments('push_project', invalid)
        validate_arguments('push_project', {'commitMessage': 'Own source change', 'files': ['src/main.zig']})
        with self.assertRaises(ValueError): validate_arguments('push_project', {'commitMessage': 'a'}, 'studio-tools-v5')

    def test_updater_accepts_additive_profile_and_preserves_rollback_contracts(self):
        spec = importlib.util.spec_from_file_location('github_update_host', Path(__file__).resolve().parents[1] / 'updates/host.py')
        host = importlib.util.module_from_spec(spec); spec.loader.exec_module(host)
        for value in (host.COMPATIBILITY, host.DEVELOPMENT_COMPATIBILITY, host.AUTHOR_COMPATIBILITY, host.UPDATE_COMPATIBILITY, host.GIT_COMPATIBILITY): self.assertTrue(host.compatible(value))
        self.assertFalse(host.compatible({**host.GIT_COMPATIBILITY, 'agentDataSchema': 2}))


if __name__ == '__main__': unittest.main()
