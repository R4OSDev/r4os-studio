"""Adversarial source/cache boundaries using real files; no target code executes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from source_checkout import Checkout, relative

spec = importlib.util.spec_from_file_location('qa_source_worker', Path(__file__).with_name('source_worker.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class SourceBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = self.root / 'Repository'
        self.repository.mkdir()
        self.checkout = Checkout(self.root, self.root / 'NoCredentials')

    def tearDown(self):
        self.temp.cleanup()

    def add(self, name, data, mode='100644'):
        oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        self.checkout.write_blob(self.repository, name, mode, oid, data, len(data))

    def manifest(self):
        value = dict(schema=1, repository='https://github.com/example/fixture', commit='a' * 40,
                     files=self.checkout.files, repositories=[], totalBytes=0)
        (self.root / 'manifest.json').write_text(json.dumps(value, ensure_ascii=True))

    def test_git_symlinks_and_posix_fixture_names_remain_inert_and_lossless(self):
        self.add('fixtures/shadow', b'/etc/shadow', '120000')
        name = 'fixtures/HFS\r/binary-' + os.fsdecode(b'\xff')
        self.add(name, b'original content')
        self.assertFalse((self.repository / 'fixtures/shadow').is_symlink())
        self.assertEqual((self.repository / 'fixtures/shadow').read_bytes(), b'/etc/shadow')
        self.assertEqual((self.repository / name).read_bytes(), b'original content')
        self.assertTrue(self.checkout.files[0]['inertLink'])
        self.manifest()
        worker.verify(self.root, 'https://github.com/example/fixture', 'a' * 40)
        for path in ('../private', '/etc/shadow', 'x/../private', '.git/config', 'a\0b'):
            with self.assertRaises(Exception):
                relative(path)

    def test_cached_source_rejects_changed_bytes_extra_files_and_live_symlinks(self):
        self.add('data.txt', b'original')
        self.manifest()
        worker.verify(self.root, 'https://github.com/example/fixture', 'a' * 40)
        (self.repository / 'data.txt').write_bytes(b'tampered')
        with self.assertRaises(worker.api.SkillFault):
            worker.verify(self.root, 'https://github.com/example/fixture', 'a' * 40)
        (self.repository / 'data.txt').unlink()
        canary = self.root / 'private.txt'
        canary.write_bytes(b'private canary')
        (self.repository / 'data.txt').symlink_to(canary)
        with self.assertRaises(worker.api.SkillFault):
            worker.verify(self.root, 'https://github.com/example/fixture', 'a' * 40)
        self.assertEqual(canary.read_bytes(), b'private canary')

    def test_lfs_pointer_is_not_misrepresented_as_materialized_binary(self):
        data = b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'c' * 64 + b'\nsize 10485760\n'
        self.add('test-corpus.bin', data)
        item = self.checkout.files[0]
        self.assertFalse(item['lfs']['materialized'])
        self.assertEqual(item['lfs']['bytes'], 10485760)
        self.assertEqual(item['bytes'], len(data))
        self.assertEqual((self.repository / 'test-corpus.bin').read_bytes(), data)
        with self.assertRaises(Exception):
            self.checkout.write_blob(self.repository, 'wrong.txt', '100644', '0' * 40, b'wrong', 5)
        self.assertFalse((self.repository / 'wrong.txt').exists())


if __name__ == '__main__':
    unittest.main()
