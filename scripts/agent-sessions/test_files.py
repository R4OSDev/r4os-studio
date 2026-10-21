import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from file_worker import execute, Fault
from tool_catalog import validate_arguments


class Files(unittest.TestCase):
    def test_scope_conflicts_and_bounded_reads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'workspace'; root.mkdir()
            (Path(temp) / 'secret').write_text('outside')
            with patch('file_worker.root_fd', side_effect=lambda _: os.open(root, os.O_RDONLY | os.O_DIRECTORY)):
                execute('create_directory', {'path': 'src/nested'})
                created = execute('write_file', {'path': 'src/nested/a.c', 'content': 'first\nsecond\n', 'expectedSha256': None})
                with self.assertRaises(Fault): execute('write_file', {'path': 'src/nested/a.c', 'content': 'lost', 'expectedSha256': None})
                with self.assertRaises(Fault): execute('read_file', {'path': '../secret'})
                (root / 'escape').symlink_to(Path(temp))
                with self.assertRaises(OSError): execute('read_file', {'path': 'escape/secret'})
                os.mkfifo(root / 'pipe')
                with self.assertRaises(Fault): execute('read_file', {'path': 'pipe'})
                read = execute('read_file', {'path': 'src/nested/a.c', 'startLine': 2, 'maxLines': 1})
                self.assertEqual(read['output'], '2: second'); self.assertEqual(read['sha256'], created['sha256'])
                with self.assertRaises(Fault): execute('apply_patch', {'patch': '*** Begin Patch\n*** Update File: src/nested/a.c\n@@\n-first\n+lost\n*** End Patch', 'expectedHashes': {}})
                self.assertEqual((root / 'src/nested/a.c').read_text(), 'first\nsecond\n')
                execute('write_file', {'path': 'src/nested/a.c', 'content': 'updated', 'expectedSha256': read['sha256']})
                self.assertEqual((root / 'src/nested/a.c').read_text(), 'updated')
                with self.assertRaises(Fault): execute('write_file', {'root': 'sdk', 'path': 'x', 'content': 'x', 'expectedSha256': None})
            for args in ({'path': '../x', 'extra': True}, {'path': 1}, {'path': 'x', 'maxLines': True}):
                with self.assertRaises(ValueError): validate_arguments('read_file', args)


if __name__ == '__main__': unittest.main()
