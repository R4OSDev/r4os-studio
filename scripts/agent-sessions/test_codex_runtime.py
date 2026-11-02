"""Default changes must not rewrite accepted runtime identities."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_runtime import binary, for_input, installed, options, selected, feature_names


class CodexRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        discovery = patch('codex_runtime.feature_names', return_value=('goals', 'image_generation'))
        discovery.start(); self.addCleanup(discovery.stop)
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
        return {'version': version, 'sha256': checksum, 'binary': str(path), 'available': True, 'toolScope': 'project', 'runtimeSelection': 1, 'runtimeFeatures': ['goals', 'image_generation']}

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
        legacy = {k: v for k, v in self.first.items() if k not in ('binary', 'runtimeSelection', 'runtimeFeatures')}
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

    def test_removed_dotted_alias_is_not_an_active_boolean_feature(self):
        output=b'goals stable false\nguardianv2.thread_context removed false\nimage_generation under development false\n'
        with patch('codex_runtime.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=output)) as probe:
            flags=feature_names.__wrapped__(self.second['binary'],self.second['sha256'])
        self.assertEqual(flags,('goals','image_generation'))
        args=probe.call_args.args[0]
        self.assertIn('--unshare-all',args);self.assertIn('--clearenv',args)

    def test_queue_revalidation_keeps_original_capture_after_default_change(self):
        import test_runs as fixtures
        from run_store import capture_input
        fixture=fixtures.Runs();fixture.setUp()
        self.addCleanup(fixture.doCleanups);self.addCleanup(fixture.tearDown)
        with fixture.open() as store:
            data={**fixture.data,'liveGoalPreparation':1}
            original,_,_=capture_input(store,fixture.sid,data,fixture.providers)
            path=fixture.r4os/'Toolchains/Codex/0.166.0/codex';path.parent.mkdir(parents=True)
            path.write_bytes(b'own-second-runtime-not-executed')
            metadata={'id':'0.166.0','version':'0.166.0','binarySha256':hashlib.sha256(path.read_bytes()).hexdigest()}
            path.with_name('.studio-component.json').write_text(json.dumps(metadata))
            (fixture.r4os/'Profiles/versions.json').write_text(json.dumps({'defaults':{'codex':{**metadata,'binary':str(path)}}}))
            fresh,_,_=capture_input(store,fixture.sid,data,fixture.providers)
            preserved,_,_=capture_input(store,fixture.sid,data,fixture.providers,original=original)
            self.assertEqual(fresh['engine']['version'],'0.166.0')
            self.assertEqual(preserved,original)
            self.assertEqual(store.row(fixture.sid)['thread_id'],None)

    def test_retry_evidence_separates_thread_creation_from_execution_runtime(self):
        import session_store
        from goal_retry_evidence import Scope,inspect_stream,UnqualifiedEvidence
        thread='00000000-0000-0000-0000-000000000001'
        turn='00000000-0000-0000-0000-000000000002'
        scope=Scope(thread,turn,'own-model',503,'a'*64,frozenset(),runtime_version='0.166.0',runtime_sha256='b'*64)
        scope.validate()
        records=[{'type':'session_meta','payload':{'id':thread,'cli_version':'0.163.0','cwd':'/workspace'}},
            {'type':'event_msg','ordinal':1,'payload':{'type':'task_started','turn_id':turn}},
            {'type':'turn_context','ordinal':2,'payload':{'turn_id':turn,'model':'own-model','cwd':'/workspace'}},
            {'type':'event_msg','ordinal':3,'payload':{'type':'task_complete','turn_id':turn,
                'error':{'codex_error_info':{'http_connection_failed':{'http_status_code':503}}}}}]
        path=self.root/'original.jsonl'
        path.write_text(''.join(json.dumps(v)+'\n' for v in records))
        with path.open('rb') as stream:proof=inspect_stream(stream,'original.jsonl',scope)
        self.assertEqual(proof['runtimeVersion'],'0.166.0');self.assertEqual(proof['runtimeSha256'],'b'*64)
        self.assertEqual(proof['threadCreationVersion'],'0.163.0')
        records[2]['ordinal']=5
        path.write_text(''.join(json.dumps(v)+'\n' for v in records))
        with path.open('rb') as stream:
            with self.assertRaises(UnqualifiedEvidence):inspect_stream(stream,'original.jsonl',scope)


if __name__ == '__main__':
    unittest.main()
