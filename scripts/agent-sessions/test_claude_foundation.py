"""Owned Claude identity/pin fixtures; no login, native model or user data."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from claude_provider_store import ClaudeProviders
from claude_runtime import binding,profile,verify
from store import ProjectFault

def request():return str(uuid.uuid4())


class ClaudeFoundation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=ClaudeProviders(self.root)

    def test_empty_reads_do_not_create_auth_homes_or_a_catalog(self):
        self.assertEqual(self.store.listing(),[]);self.assertFalse(self.store.root.exists())
        with self.assertRaises(ProjectFault):self.store.receipt(request())
        self.assertFalse(self.store.root.exists())

    def test_original_creation_receipt_and_immutable_native_identity_do_not_copy_tokens(self):
        payload={'requestId':request(),'name':'Own Claude plan'}
        with patch('claude_provider_store.installed',return_value={'id':profile()['id']}):
            result=self.store.create(payload)
        provider=result['provider'];self.assertEqual(self.store.get(provider['id']),provider)
        self.assertEqual(self.store.create(payload),result);self.assertEqual(self.store.receipt(payload['requestId']),result)
        self.assertEqual(provider['type'],'claude-subscription');self.assertIsNone(provider['account'])
        self.assertIs(provider['enabled'],False);self.assertEqual(provider['auth'],{'kind':'native-plan','state':'not-connected'})
        self.assertEqual(list(self.store.root.iterdir()),[self.store.root/'Providers.sqlite'])
        with self.assertRaises(ProjectFault):self.store.create({**payload,'name':'Changed original input'})
        sid=request();native=request();frozen=binding(provider,sid,native)
        self.assertEqual(frozen['kind'],'claude-code');self.assertEqual(frozen['nativeSessionId'],native)
        self.assertEqual(frozen['studioSessionId'],sid);self.assertEqual(frozen['version'],'2.1.312')
        self.assertEqual(frozen['sdkVersion'],'0.3.312');self.assertNotIn('baseUrl',frozen)
        for change in ({'type':'api'},{'profileRevision':True},{'profileRevision':2},{'runtimeProfileId':'other-runtime'}):
            with self.assertRaises(ProjectFault):binding({**provider,**change},sid,native)
        self.assertEqual((self.store.root/'Providers.sqlite').stat().st_mode&0o777,0o600)

    def test_api_keys_tokens_and_unknown_fields_are_refused_before_storage(self):
        for extra in ({'key':'owned-fixture'},{'token':'owned-fixture'},{'baseUrl':'https://example.test'}, {'kind':'openrouter'}):
            with self.assertRaises(ProjectFault):self.store.create({'requestId':request(),'name':'Own plan',**extra})
        self.assertFalse(self.store.root.exists())

    def fake_runtime(self):
        expected=copy.deepcopy(profile());path=self.root/'OwnRuntime';path.mkdir(mode=0o700)
        for kind,filename in (('sdk','sdk.mjs'),('native','claude')):
            folder=path/kind;folder.mkdir(mode=0o700);file=folder/filename;data=b'only owned integrity fixture\n'
            file.write_bytes(data);file.chmod(0o700 if kind=='native' else 0o600)
            expected[kind]['files']={filename:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'executable':kind=='native'}}
        manifest=path/'profile.json';manifest.write_text(json.dumps(expected));manifest.chmod(0o600)
        return path,expected

    def test_changed_missing_or_linked_runtime_preserves_original_files(self):
        path,expected=self.fake_runtime();self.assertEqual(verify(path,expected)['id'],expected['id'])
        native=path/'native/claude';original=native.read_bytes();native.write_bytes(b'changed pinned bytes')
        with self.assertRaises(ProjectFault):verify(path,expected)
        self.assertEqual(native.read_bytes(),b'changed pinned bytes')
        native.write_bytes(original);native.chmod(0o700)
        original_file=self.root/'owned-native-original';native.rename(original_file);native.symlink_to(original_file)
        with self.assertRaises(ProjectFault):verify(path,expected)
        self.assertEqual(original_file.read_bytes(),original)

    def test_runtime_profile_keeps_authenticated_turns_tools_and_limits_unqualified(self):
        value=profile()
        self.assertEqual(value['sdk']['version'],'0.3.312');self.assertEqual(value['native']['version'],'2.1.312')
        for key in ('authenticatedSubscription','modelTurns','studioTools','goals','overageProtection'):
            self.assertIs(value['qualified'][key],False)
        self.assertEqual(len(value['native']['files']['claude']['sha256']),64)
        self.assertEqual(value['native']['files']['claude']['bytes'],293592432)
