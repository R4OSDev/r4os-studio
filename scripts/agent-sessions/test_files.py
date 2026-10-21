import os
import json
import subprocess
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from file_worker import execute, failure, Fault
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

    def test_search_reports_skipped_large_or_non_text_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'large.txt').write_text('needle'+'x'*300000); (root/'small.txt').write_text('needle'); (root/'binary').write_bytes(b'\xff\xfe')
            with patch('file_worker.root_fd', side_effect=lambda _: os.open(root, os.O_RDONLY | os.O_DIRECTORY)):
                result = execute('search', {'path': '.', 'query': 'needle'})
            self.assertTrue(result['truncated']); self.assertEqual(result['skippedFiles'], 2)
            self.assertEqual([r['path'] for r in json.loads(result['output'])], ['./small.txt'])

    def test_fsync_failure_after_publication_is_an_unconfirmed_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); calls = []
            def fail_directory_sync(fd):
                calls.append(fd)
                if len(calls) == 2: raise OSError('directory fsync failed')
            with patch('file_worker.root_fd', side_effect=lambda _: os.open(root, os.O_RDONLY | os.O_DIRECTORY)), patch('file_worker.os.fsync', side_effect=fail_directory_sync):
                try: execute('write_file', {'path': 'published.c', 'content': 'retained', 'expectedSha256': None})
                except OSError as error: result = failure('write_file', error)
                else: self.fail('Expected post-publication failure')
            self.assertEqual((root/'published.c').read_text(), 'retained')
            self.assertEqual(result['error'], 'unknown'); self.assertTrue(result['partialChangesPossible'])

    def test_read_page_limits_report_continuation_without_skipping_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'large.txt').write_text('\n'.join('line-'+str(i)+' '+'x'*1500 for i in range(400)))
            with patch('file_worker.root_fd', side_effect=lambda _: os.open(root, os.O_RDONLY | os.O_DIRECTORY)):
                numbers = []; start = 1; hashes = set()
                while True:
                    page = execute('read_file', {'path': 'large.txt', 'startLine': start, 'maxLines': 500})
                    self.assertLessEqual(len(page['output'].encode()), 60000)
                    numbers.extend(int(line.split(': ', 1)[0]) for line in page['output'].splitlines())
                    hashes.add(page['sha256'])
                    if page['nextLine'] is None: break
                    self.assertTrue(page['truncated']); self.assertGreater(page['nextLine'], start); start = page['nextLine']
                self.assertEqual(numbers, list(range(1,401))); self.assertEqual(len(hashes), 1)
                (root/'long-line.txt').write_text('🦀'*20000+'\nend')
                page = execute('read_file', {'path': 'long-line.txt'})
                self.assertTrue(page['truncated']); self.assertEqual(page['lineTruncated'], 1); self.assertEqual(page['nextLine'], 2)
                self.assertLessEqual(len(page['output'].encode()), 60000)
                self.assertEqual(execute('read_file', {'path': 'long-line.txt', 'startLine': 2})['output'], '2: end')


@unittest.skipIf(os.getuid()==0, 'Run real patch namespace checks as the unprivileged service user.')
class PatchNamespace(unittest.TestCase):
    def test_official_patch_moves_deletes_and_reports_failure_files(self):
        binary = Path(__file__).resolve().parents[2]/'Data/R4OS/Toolchains/Codex/0.163.0/codex'
        if not binary.exists(): self.skipTest('Qualified Codex is not installed.')
        with binary.open('rb') as stream: self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(), '399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'a.c').write_text('old\n'); (root/'b.c').write_text('other\n')
            args=['/usr/bin/bwrap','--die-with-parent','--unshare-pid','--unshare-net']
            for path in ('/usr','/lib','/lib64'):
                if Path(path).exists(): args+=['--ro-bind',path,path]
            args+=['--symlink','/usr/bin','/bin','--dev','/dev','--proc','/proc','--tmpfs','/tmp','--dir','/home/studio',
                   '--bind',str(root),'/workspace','--ro-bind',str(binary),'/runner/codex',
                   '--ro-bind',str(Path(__file__).with_name('file_worker.py')),'/runner/file_worker.py','--chdir','/workspace',
                   '--clearenv','--setenv','HOME','/home/studio','/usr/bin/python3','-I','-B','/runner/file_worker.py']
            def call(text,hashes):
                result=subprocess.run(args,input=json.dumps({'tool':'apply_patch','arguments':{'patch':text,'expectedHashes':hashes}}),text=True,capture_output=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
            sha=lambda path:hashlib.sha256((root/path).read_bytes()).hexdigest()
            result=call('*** Begin Patch\n*** Update File: a.c\n@@\n-old\n+new\n*** Update File: b.c\n@@\n-not present\n+wrong\n*** End Patch',{'a.c':sha('a.c'),'b.c':sha('b.c')})
            self.assertFalse(result['success']);self.assertTrue(result['partialChangesPossible']);self.assertEqual(result['files'],{'a.c':sha('a.c'),'b.c':sha('b.c')})
            old=(root/'a.c').read_text().strip()
            result=call('*** Begin Patch\n*** Update File: a.c\n*** Move to: nested/moved.c\n@@\n-'+old+'\n+moved\n*** End Patch',{'a.c':sha('a.c')})
            self.assertTrue(result['success'],result);self.assertFalse((root/'a.c').exists());self.assertEqual((root/'nested/moved.c').read_text(),'moved\n')
            result=call('*** Begin Patch\n*** Delete File: nested/moved.c\n*** End Patch',{'nested/moved.c':sha('nested/moved.c')})
            self.assertTrue(result['success'],result);self.assertIsNone(result['files']['nested/moved.c']);self.assertFalse((root/'nested/moved.c').exists())


if __name__ == '__main__': unittest.main()
