"""Focused final negative/readback checks; no network, inference or user data."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import uuid
import test_git as fixtures
from common import ProjectFault, save
from operations import Operations


class FailureTests(unittest.TestCase):
    setUp = fixtures.GitTests.setUp
    tearDown = fixtures.GitTests.tearDown
    job = fixtures.GitTests.job

    def test_auth_rate_network_and_redirect_errors_never_echo_credentials(self):
        from github import GitHub
        directory = Path(self.config['github']); directory.mkdir()
        identity = str(uuid.uuid4()); token = 'own-fixture-not-a-real-secret-token'
        save(directory / 'connections.json', {'schema': 1, 'connections': [{'id': identity, 'name': 'Own fixture', 'token': token, 'tokenRevision': 1}]})
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps({'id': 7, 'login': 'octocat'}).encode()
        cases = [(HTTPError('https://api.github.com/user', code, token, {}, None), code if code in (401, 403, 429) else 502) for code in (401, 403, 429, 302)]
        cases.append((URLError(token), 503))
        for failure, expected in cases:
            with self.subTest(code=expected), patch('github.build_opener') as factory:
                factory.return_value.open.side_effect = [Response(), failure]
                api = GitHub(directory, identity, 1, 7)
                with self.assertRaises(ProjectFault) as raised: api.request('/repos/octocat/own-qa')
                self.assertEqual(raised.exception.code, expected); self.assertNotIn(token, str(raised.exception))
                self.assertTrue(factory.return_value.open.call_args.args[0].full_url.startswith('https://api.github.com/'))

    def test_commit_readback_before_and_after_ref_publication_does_not_repeat_commit(self):
        from pushing import reconcile
        action = Operations(self.config, self.job('push')); action.initialize()
        action.bound = {'schema': 1, 'revision': 1, 'connectionId': str(uuid.uuid4()), 'userId': 7, 'repository': {'id': 11}, 'branch': 'main', 'author': {'name': 'Own QA', 'email': 'qa@example.invalid'}}
        action.git.run('add', '--all'); tree = action.git.text('write-tree')
        commit = action.git.text('-c', 'user.name=Own QA', '-c', 'user.email=qa@example.invalid', 'commit-tree', tree, data=b'Own prepared commit\n')
        action.job.update(preparedCommit=commit, previousHead=None)
        before = reconcile(action); self.assertTrue(before['notPublished']); self.assertFalse(before['committed']); self.assertIsNone(action.git.head())
        action.job = self.job('push'); action.job.update(preparedCommit=commit, previousHead=None)
        action.git.run('update-ref', 'HEAD', commit, '0' * 40)
        with patch.object(action, 'fetch', side_effect=AssertionError('No remote write had been attempted.')):
            after = reconcile(action); self.assertTrue(after['localCommitOnly']); self.assertFalse(after['pushed']); self.assertEqual(reconcile(action), after)
        self.assertEqual(action.git.text('rev-list', '--count', 'HEAD'), '1')

    def test_import_rejects_case_collisions_in_directory_prefixes(self):
        from trees import entries
        action = Operations(self.config, self.job()); action.initialize()
        for name in ('Case/one.txt', 'case/two.txt'):
            path = self.source / name; path.parent.mkdir(exist_ok=True); path.write_text('Own fixture\n')
        action.git.run('add', '--all'); action.git.run('-c', 'user.name=Own QA', '-c', 'user.email=qa@example.invalid', 'commit', '--no-gpg-sign', '-m', 'Case fixture')
        with self.assertRaises(ProjectFault): entries(action.git, action.git.head())

    def test_existing_repository_name_is_rejected_before_any_create_effect(self):
        class Existing:
            def __init__(self, *args): self.user = {'id': 7, 'login': 'octocat'}
            def repository(self, *args): return {'id': 11, 'fullName': 'octocat/own-qa'}
            def request(self, *args): raise AssertionError('An existing repository must never be created or overwritten.')
        action = Operations(self.config, self.job('create_repository'))
        with patch('operations.GitHub', Existing), self.assertRaises(ProjectFault) as raised:
            action.create_repository({'connectionId': str(uuid.uuid4()), 'tokenRevision': 1, 'userId': 7, 'repositoryName': 'own-qa', 'private': True})
        self.assertEqual(raised.exception.code, 422); self.assertFalse((action.base / 'create-repository.json').exists())
        self.assertEqual((self.source / 'module.R4MF').read_text(), 'test manifest\n')


if __name__ == '__main__': unittest.main()
