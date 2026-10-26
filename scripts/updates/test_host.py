import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import host


class HostTests(unittest.TestCase):
    def test_agent_protocol_requires_explicit_supported_contract(self):
        legacy = host.COMPATIBILITY.copy()
        self.assertTrue(host.compatible(legacy))
        self.assertTrue(host.compatible({**legacy, **host.AGENT_COMPATIBILITY}))
        self.assertFalse(host.compatible({**legacy, 'agentWorkerProtocol': 1}))
        self.assertFalse(host.compatible({**legacy, **host.AGENT_COMPATIBILITY, 'agentDataSchema': 2}))
        self.assertFalse(host.compatible({**legacy, 'unknownProtocol': 1}))
        self.assertTrue(host.compatible(host.DEVELOPMENT_COMPATIBILITY))
        self.assertTrue(host.compatible(host.SKILL_COMPATIBILITY))
        self.assertTrue(host.compatible(host.AUTHOR_COMPATIBILITY))
        self.assertTrue(host.compatible(host.UPDATE_COMPATIBILITY))
        self.assertEqual(json.loads((Path(__file__).resolve().parents[2]/'shared/update-host.json').read_text()),host.UPDATE_COMPATIBILITY)
        self.assertFalse(host.compatible({**host.SKILL_COMPATIBILITY, 'agentDataSchema': 2}))
        self.assertFalse(host.compatible({**host.DEVELOPMENT_COMPATIBILITY, 'developmentDataSchema': 2}))
        self.assertFalse(host.compatible({**host.DEVELOPMENT_COMPATIBILITY, 'agentToolProfiles': ['unqualified']}))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.base, self.state = root / 'opt', root / 'state'
        (self.base / 'releases').mkdir(parents=True)
        self.state.mkdir()
        self.patch = patch.multiple(host, BASE=self.base, STATE=self.state)
        self.patch.start()
        self.commands = patch.object(host, 'run', side_effect=AssertionError('Unexpected host command in a unit test'))
        self.commands.start()
        self.old = self.release('0.1.15', 'old')
        self.new = self.release('0.1.16', 'new')
        host.switch(self.old)
        self.manager = host.Updater({'repository': 'https://example.test/app.git', 'checkIntervalSeconds': 21600})
        self.data = root / 'App/Data/R4OS/Instances/vm/Exchange/Share'
        self.data.mkdir(parents=True)
        (self.data / 'PERSIST.TXT').write_text('guest data')
        self.inode = (self.data / 'PERSIST.TXT').stat().st_ino

    def tearDown(self):
        self.assertEqual((self.data / 'PERSIST.TXT').read_text(), 'guest data')
        self.assertEqual((self.data / 'PERSIST.TXT').stat().st_ino, self.inode)
        self.patch.stop()
        self.commands.stop()
        self.temp.cleanup()

    def release(self, version, identity):
        path = self.base / 'releases' / identity
        path.mkdir()
        host.atomic_json(path / 'release.json', {'version': version, 'commit': 'a' * 40, 'id': identity})
        return path

    def test_numeric_stable_tags_and_annotated_peeling(self):
        values = host.releases('\n'.join([
            'b' * 40 + '\trefs/tags/v0.1.9', 'c' * 40 + '\trefs/tags/v0.1.10',
            'd' * 40 + '\trefs/tags/v0.1.10^{}', 'e' * 40 + '\trefs/tags/v99.0.0-beta',
            'f' * 40 + '\trefs/tags/v01.2.3', 'a' * 40 + '\trefs/heads/main']))
        self.assertEqual([value['version'] for value in values], ['0.1.9', '0.1.10'])
        self.assertEqual(values[-1]['commit'], 'd' * 40)

    def test_inactive_unloaded_builder_is_not_reset_but_failed_builder_is(self):
        with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            host.reset_build_failure()
        with patch.object(host.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), patch.object(host, 'run') as command:
            host.reset_build_failure()
        command.assert_called_once_with(['/usr/bin/systemctl', 'reset-failed', host.BUILD_UNIT])

    def test_successful_activation_restarts_only_web_service(self):
        with patch.object(host, 'run') as command, patch.object(self.manager, 'healthy') as health:
            self.assertTrue(self.manager.activate(self.new))
        self.assertEqual([call.args[0] for call in command.call_args_list], [
            ['/usr/bin/systemctl', 'reset-failed', 'r4os-studio.service'],
            ['/usr/bin/systemctl', 'restart', 'r4os-studio.service']])
        self.assertEqual((self.base / 'current').resolve(), self.new)
        self.assertEqual(health.call_args.args[0]['version'], '0.1.16')
        self.assertFalse((self.state / 'transaction.json').exists())

    def test_unhealthy_release_rolls_back_and_checks_previous_version(self):
        with patch.object(self.manager, 'restart') as restart, patch.object(self.manager, 'healthy', side_effect=[RuntimeError('bad release'), None]) as health:
            self.assertFalse(self.manager.activate(self.new))
        self.assertEqual(restart.call_count, 2)
        self.assertEqual([call.args[0]['version'] for call in health.call_args_list], ['0.1.16', '0.1.15'])
        self.assertEqual((self.base / 'current').resolve(), self.old)
        self.assertEqual(self.manager.status()['phase'], 'rolled_back')
        self.assertFalse((self.state / 'transaction.json').exists())

    def test_failed_rollback_retains_transaction_for_recovery(self):
        with patch.object(self.manager, 'restart'), patch.object(self.manager, 'healthy', side_effect=RuntimeError('unhealthy')):
            with self.assertRaisesRegex(RuntimeError, 'host attention'):
                self.manager.activate(self.new)
        self.assertTrue((self.state / 'transaction.json').exists())
        with patch.object(host.Updater, 'restart'), patch.object(host.Updater, 'healthy'):
            host.Updater(self.manager.config).recover()
        self.assertEqual((self.base / 'current').resolve(), self.old)
        self.assertFalse((self.state / 'transaction.json').exists())

    def test_changed_remote_tag_never_builds_or_switches(self):
        latest = {'version': '0.1.16', 'tag': 'v0.1.16', 'commit': 'b' * 40}
        self.manager.state['latest'] = latest
        with patch.object(self.manager, 'discover', return_value=latest), patch.object(host, 'run') as command:
            with self.assertRaisesRegex(RuntimeError, 'selected update has changed'):
                self.manager.install({'tag': 'v0.1.16', 'commit': 'a' * 40})
        command.assert_not_called()
        self.assertEqual((self.base / 'current').resolve(), self.old)

    def test_escaping_build_symlink_is_rejected(self):
        source = Path(self.temp.name) / 'source'
        source.mkdir()
        (source / 'escape').symlink_to(self.data)
        with self.assertRaisesRegex(RuntimeError, 'link outside'):
            host.copy_release(source, self.base / 'releases/rejected')


if __name__ == '__main__':
    unittest.main()
