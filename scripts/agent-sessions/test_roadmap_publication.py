"""Frozen local publication context and original receipts, without inference/network."""
import copy
import hashlib
import unittest
import uuid
from unittest.mock import patch
import test_tool_defaults as fixtures
from instructions import compose
from roadmap_instructions import compose as roadmap
from github_tools import publication_receipt
from run_store import admit, get_run
from profile import PROFILE
import json


class Publication(unittest.TestCase):
    setUp = fixtures.Defaults.setUp
    tearDown = fixtures.Defaults.tearDown
    open = fixtures.Defaults.open
    binding = fixtures.Defaults.binding
    create = fixtures.Defaults.create

    def test_effective_contract_freezes_private_binding_and_preserves_saved_sources_on_resume(self):
        with self.open() as store, patch('session_store.engine', return_value={'profile': PROFILE, 'available': True}):
            _, binding = self.binding()
            session = self.create(store)
            run, _ = admit(store, session['id'], {'requestId': str(uuid.uuid4()), 'revision': session['revision'], 'text': 'Work through the roadmap', 'roadmapSettings': 1}, self.providers)
            config = json.loads(get_run(store, run['id'])['config'])
            self.assertEqual(config['githubBinding']['revision'], binding['revision'])
            self.assertEqual(config['githubBinding']['repository']['id'], 11)
            original = copy.deepcopy(config)
            text = compose(config)
            self.assertIn('STUDIO PUBLICATION CONTEXT: enabled.', text)
            self.assertIn('autonomously commit and push each subversion', text)
            self.assertIn('all required checks have passed', text)
            self.assertIn('meaningful commitMessage that includes the subversion number', text)
            self.assertIn('nothingToPush', text); self.assertIn('original job/request ID', text)
            self.assertIn('do not blindly use a new call ID', text)
            self.assertNotIn(binding['connectionId'], text)
            self.assertEqual(config, original)
            self.assertEqual(compose(config), text)  # same contract before native start/resume
            self.assertEqual(hashlib.sha256(config['projectInstructions']['text'].encode()).hexdigest(), config['projectInstructions']['sha256'])
            for changed, reason in [({'permissions': {}}, 'Push is not permitted'), ({'githubBinding': None}, 'no confirmed frozen repository'), ({}, 'no confirmed frozen repository')]:
                value = {**config, **changed}
                if not changed: value.pop('githubBinding')
                self.assertIn('STUDIO PUBLICATION CONTEXT: disabled.', roadmap(value)); self.assertIn(reason, roadmap(value))
            self.assertNotIn('CHECKED SUBVERSION PUBLICATION', roadmap({**config, 'roadmapEnabled': False}))
            self.assertNotIn('CHECKED SUBVERSION PUBLICATION', roadmap({**config, 'engine': {'profile': 'studio-tools-v1'}}))
            self.assertEqual(roadmap({**config, 'owner': {'type': 'skill', 'id': self.pid}}), '')

    def test_only_original_completed_publication_or_noop_is_success(self):
        identity, project = str(uuid.uuid4()), str(uuid.uuid4())
        base = {'id': identity, 'projectId': project, 'kind': 'push', 'state': 'completed', 'result': {'pushed': True, 'commit': 'a' * 40, 'remoteHead': 'b' * 40}}
        self.assertTrue(publication_receipt(base, identity, project)['success'])
        noop = publication_receipt({**base, 'result': {'pushed': False, 'nothingToPush': True, 'commit': None, 'remoteHead': None}}, identity, project)
        self.assertTrue(noop['success']); self.assertTrue(noop['github']['nothingToPush'])
        self.assertIn('No empty commit', noop['output'])
        for value in ({**base, 'state': 'unknown'}, {**base, 'id': str(uuid.uuid4())}, {**base, 'projectId': str(uuid.uuid4())}, {**base, 'result': {'pushed': True, 'commit': 'a' * 40}}, {**base, 'result': {'localCommitOnly': True, 'commit': 'a' * 40}}, {**base, 'result': {'notPublished': True}}):
            self.assertFalse(publication_receipt(value, identity, project)['success'])


if __name__ == '__main__': unittest.main()
