"""Lifecycle receipts, captured bytes and test outcomes are independent."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from checks import evaluate
from execution import Execution
from execution_evidence import describe
from layout import save


class ExecutionEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.job = {'id': 'job', 'kind': 'execution', 'executionId': 'execution',
            'deploymentId': 'deployment', 'target': {'bootId': 'original-boot'},
            'settings': {'expectedExitCode': 0, 'outputContains': ['EXPECTED']},
            'process': {'instanceId': 4, 'generation': '18446744073709551615'}}
        self.intent = {**{key: self.job[key] for key in ('executionId', 'deploymentId', 'target', 'settings')},
            'schema': 1, 'jobId': self.job['id'], 'state': 'intent'}
        self.work = self.root / 'ExecutionWork/job'; self.work.mkdir(parents=True)
        self.log = self.root / 'Evidence/job/output.log'; self.log.parent.mkdir(parents=True)
        save(self.work / 'intent.json', self.intent)
        save(self.work / 'started.json', {**self.intent, 'state': 'started', 'process': self.job['process']})
        self.state = {**self.job['process'], 'state': 'completed', 'closeConfirmed': True,
            'exitCode': None, 'outputIncomplete': True, 'exitEvidenceUnavailable': True}

    def closed(self, data=b'', state=None):
        self.log.write_bytes(data)
        value = {**self.intent, 'state': 'closed', 'completion': state or self.state,
            'cleanupReceipt': {'closed': True, 'serviceRemoved': True, 'watchdogRemoved': True},
            'outputReceipt': {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}
        save(self.work / 'closed.json', value)
        return value

    def read(self): return describe(SimpleNamespace(root=self.root), copy.deepcopy(self.job))

    def test_empty_unconfirmed_output_is_not_a_successful_exit_or_text_check(self):
        self.closed(); originals = {p: p.read_bytes() for p in self.work.iterdir()}
        result = self.read()
        self.assertTrue(result['processEndConfirmed']); self.assertTrue(result['cleanupConfirmed'])
        self.assertFalse(result['exitStatusConfirmed']); self.assertIsNone(result['exitCode'])
        self.assertEqual(result['output']['state'], 'incomplete')
        self.assertEqual(evaluate(self.job['settings'], self.state, b'')['state'], 'inconclusive')
        self.assertEqual({p: p.read_bytes() for p in self.work.iterdir()}, originals)
        complete = {**self.state, 'exitCode': 0, 'outputIncomplete': False, 'completionObserved': True}
        self.closed(state=complete)
        self.assertEqual(self.read()['output']['state'], 'complete')
        self.assertEqual(evaluate(self.job['settings'], complete, b'')['state'], 'failed')

    def test_foreign_or_damaged_receipts_cannot_certify_lifecycle(self):
        for change in ('generation', 'boot', 'execution', 'schema', 'cleanup', 'missing', 'malformed'):
            with self.subTest(change=change):
                value = self.closed()
                if change == 'generation': value['completion'] = {**self.state, 'generation': '3'}
                if change == 'boot': value['target'] = {'bootId': 'different-boot'}
                if change == 'execution': value['executionId'] = 'different-execution'
                if change == 'schema': value['schema'] = True
                if change == 'cleanup': value['cleanupReceipt']['watchdogRemoved'] = False
                save(self.work / 'closed.json', value)
                if change == 'missing': (self.work / 'closed.json').unlink()
                if change == 'malformed': (self.work / 'closed.json').write_text('[]')
                result = self.read()
                self.assertFalse(result['cleanupConfirmed'])
                self.assertEqual(result['processEndConfirmed'], change == 'cleanup')

    def test_observed_completion_survives_observer_loss_without_claiming_cleanup(self):
        worker = Execution.__new__(Execution)
        worker.intent = self.intent; worker.output_observation = None; worker.work = self.work
        worker.log = self.log; worker.output_data = b''; worker.output_limited = False
        state = {**self.state, 'exitCode': 0, 'completionObserved': True, 'outputIncomplete': False,
            'controllerSequence': 3, 'outputBase64': base64.b64encode(b'EXPECTED').decode()}
        worker.output(state)
        # A fresh reader has only original files, not the observer's memory.
        result = self.read()
        self.assertTrue(result['processEndConfirmed']); self.assertFalse(result['cleanupConfirmed'])
        self.assertTrue(result['exitStatusConfirmed']); self.assertEqual(result['output']['bytes'], 8)
        self.assertEqual(result['source'], 'private-guest-observation')
        self.assertEqual(result['output']['state'], 'complete')
        self.assertNotIn('outputBase64', json.loads((self.work / 'output-observation.json').read_text())['observation'])
        # A caller still holding the pre-capture frame must not overwrite the
        # newer completion or append its old bytes a second time.
        worker.output({**state, 'state': 'running', 'closeConfirmed': False, 'controllerSequence': 2})
        worker.output(state)
        self.assertEqual(worker.output_data, b'EXPECTED')
        self.assertTrue(self.read()['processEndConfirmed'])

    def test_changed_output_preserves_closure_but_invalidates_text_completeness(self):
        self.closed(b'EXPECTED', {**self.state, 'exitCode': 0, 'completionObserved': True, 'outputIncomplete': False})
        self.log.write_bytes(b'tampered')
        result = self.read()
        self.assertTrue(result['cleanupConfirmed'])
        self.assertEqual(result['output']['state'], 'unconfirmed')
