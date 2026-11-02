"""Default changes must not rewrite accepted runtime identities."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from codex_runtime import binary, for_input, installed, options, selected


class CodexRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'Profiles').mkdir()
        self.first = self.install('0.163.0', b'first-original-binary')
        self.second = self.install('0.166.0', b'second-original-binary')
        self.choose(self.first)
        self.store = SimpleNamespace(r4os=self.root)
        self.session = {'engine': self.first, 'owner': {'type': 'project'}, 'threadId': 'same-native-thread'}

    def install(self, version, data):
        path = self.root / 'Toolchains/Codex' / version / 'codex'
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        checksum = hashlib.sha256(data).hexdigest()
        (path.parent / '.studio-component.json').write_text(json.dumps(
            {'id': version, 'version': version, 'binarySha256': checksum}))
        return {'version': version, 'sha256': checksum, 'binary': str(path), 'available': True, 'toolScope': 'project', 'runtimeSelection': 1}

    def choose(self, engine):
        (self.root / 'Profiles/versions.json').write_text(json.dumps({'defaults': {'codex': {
            'id': engine['version'], 'version': engine['version'],
            'binary': engine['binary'], 'binarySha256': engine['sha256']}}}))

    def test_current_default_and_scope_without_release_allowlist(self):
        self.choose(self.second)
        self.assertEqual(selected(self.root, 'skill'), {**self.second, 'toolScope': 'skill'})

    def test_new_input_switches_without_replacing_thread(self):
        self.choose(self.second)
        result = for_input(self.store, self.session)
        self.assertEqual(result['engine'], self.second)
        self.assertEqual(result['threadId'], self.session['threadId'])
        self.assertEqual(self.session['engine'], self.first)

    def test_accepted_queue_keeps_exact_legacy_engine_bytes(self):
        legacy = {k: v for k, v in self.first.items() if k not in ('binary', 'runtimeSelection')}
        self.choose(self.second)
        result = for_input(self.store, self.session, {'engine': legacy})
        self.assertEqual(result['engine'], legacy)
        self.assertEqual(binary(self.root, legacy), Path(self.first['binary']))

    def test_missing_default_never_falls_back(self):
        Path(self.first['binary']).unlink()
        self.assertFalse(options(self.root, 'project')['available'])
        with self.assertRaises(OSError): for_input(self.store, self.session)

    def test_original_binary_bytes_are_checked_again(self):
        Path(self.first['binary']).write_bytes(b'changed')
        self.choose(self.second)
        with self.assertRaises(ValueError): for_input(self.store, self.session, {'engine': self.first})

    def test_frozen_hash_cannot_be_rebound_to_replaced_installation(self):
        old = self.first.copy()
        path = Path(old['binary'])
        path.write_bytes(b'replacement')
        metadata = {'id': old['version'], 'version': old['version'], 'binarySha256': hashlib.sha256(b'replacement').hexdigest()}
        path.with_name('.studio-component.json').write_text(json.dumps(metadata))
        with self.assertRaises(ValueError): installed(path, old)

    def test_default_path_and_metadata_cannot_disagree(self):
        self.choose({**self.first, 'binary': self.second['binary']})
        self.assertFalse(options(self.root, 'project')['available'])
        with self.assertRaises(ValueError): binary(self.root, {**self.first, 'version': '../outside'})

    def test_api_route_preserved_and_claude_runtime_separate(self):
        api = {'providerId': 'original', 'baseUrl': 'https://example.invalid', 'protocol': 'responses'}
        self.choose(self.second)
        result = for_input(self.store, {**self.session, 'engine': {**self.first, 'api': api}})
        self.assertEqual(result['engine'], {**self.second, 'api': api})
        claude = {'engine': {'kind': 'claude-code'}}
        self.assertIs(for_input(self.store, claude), claude)


if __name__ == '__main__':
    unittest.main()
