import json,tempfile,unittest
from pathlib import Path
from protocol import supported_profiles,validate_release

class ProtocolTest(unittest.TestCase):
    def test_v1_rollback_and_v2_worker_identity_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'release';(root/'shared').mkdir(parents=True);(root/'scripts/agent-sessions').mkdir(parents=True);(root/'scripts/agent-sessions/worker.py').write_text('fixture')
            def write(version,profiles=None):
                value={'agentHostProtocol':1,'agentWorkerProtocol':1,'agentDataSchema':1}
                if profiles is not None:value['agentToolProfiles']=profiles
                (root/'shared/update-host.json').write_text(json.dumps(value));(root/'shared/version.json').write_text(json.dumps({'version':version}));(root/'release.json').write_text(json.dumps({'id':'identity','version':version}))
            write('0.3.23');self.assertEqual(supported_profiles(root),('studio-tools-v1',));write('0.3.24');self.assertEqual(len(supported_profiles(root)),2)
            write('0.3.25',['studio-tools-v1','studio-tools-v2']);value={'releaseRoot':str(root),'release':'identity','version':'0.3.25'};validate_release(value,Path(temp))
            with self.assertRaises(ValueError):validate_release({**value,'release':'different'},Path(temp))
            write('0.3.26',['unqualified']);
            with self.assertRaises(ValueError):supported_profiles(root)
