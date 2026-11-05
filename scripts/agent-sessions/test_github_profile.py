"""Push schema validation for the current common Studio catalog."""
import unittest
from tool_catalog import validate_arguments


class GitHubProfileTest(unittest.TestCase):
    def test_push_arguments_reject_empty_messages_credentials_and_oversized_text(self):
        selected = {'selectionId': 'a' * 64}
        for invalid in ({}, {**selected, 'commitMessage': ''}, {**selected, 'commitMessage': 'a', 'token': 'forbidden'}, {**selected, 'commitMessage': 'a' * 4001}):
            with self.assertRaises(ValueError): validate_arguments('push_project', invalid)
        validate_arguments('push_project', {**selected, 'commitMessage': 'Own source change'})


if __name__ == '__main__': unittest.main()
