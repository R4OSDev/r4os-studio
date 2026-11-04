"""Exercise real publication, immutable identities and rollback in private stores."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publication_test_store', Path(__file__).with_name('store.py'))
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)
from source_publish import publish


class Publications(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'Skills'
        self.db = api.connect(self.root)
        self.ident = str(uuid.uuid4())
        api.create(self.db, self.root, dict(id=self.ident, name='Source qualification'))
        api.sources.configure(self.db, self.root, dict(id=self.ident, revision=1,
            source={'repository': 'https://github.com/example/qualification', 'skillPath': 'skill'},
            requestId=str(uuid.uuid4())), api)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def job(self):
        detail = api.detail(self.db, self.root, self.ident)
        return api.sources.prepare(self.db, self.root, dict(id=self.ident, revision=detail['skill']['revision'],
            sourceRevision=detail['source']['revision'], draftHash=detail['draftHash'],
            requestId=str(uuid.uuid4()), action='update'), api)

    def source(self, commit, content='Use the supplied project data.'):
        source = api.folder(self.root / self.ident / 'Sources' / (commit * 40), True)
        package = api.folder(source / 'Repository' / 'skill', True)
        api.atomic(package / 'SKILL.md', ('---\nname: source-qualification\ndescription: Analyze supplied project data.\n---\n\n'
                   + content + '\nSee [guide](references/guide.md).\n').encode())
        api.atomic(api.folder(package / 'references', True) / 'guide.md', b'Complete relative resource.\n')
        files = api.inventory(package)[0]
        manifest = dict(schema=1, repository='https://github.com/example/qualification', commit=commit * 40,
                        files=[dict(f, path='skill/' + f['path']) for f in files], repositories=[], totalBytes=0)
        return source, manifest, api.digest(api.encode(manifest).encode())

    def apply(self, job, source):
        return publish(api, self.db, self.root, self.ident, job, *source, lambda **_: None)

    def end(self, job):
        job = dict(job, phase='complete')
        self.db.execute('UPDATE skill_source_jobs SET metadata=? WHERE request_id=?', (api.encode(job), job['requestId']))
        self.db.commit()

    def test_complete_publication_commit_change_noop_and_local_save(self):
        source = self.source('a')
        job = self.job()
        first = self.apply(job, source)
        self.end(job)
        self.assertTrue(first['published'])
        current = api.detail(self.db, self.root, self.ident)
        original = current['skill']['activeHash']
        immutable = self.root / self.ident / 'Revisions' / original / 'Workspace'
        self.assertEqual(current['draftHash'], current['activeDraftHash'])
        self.assertNotEqual(current['draftHash'], original)
        self.assertTrue((immutable / 'references/guide.md').is_file())
        snapshot = json.loads((immutable.parent / 'revision.json').read_text())
        self.assertEqual(snapshot['sourceBinding']['commit'], 'a' * 40)
        self.assertEqual(api.source_binding.package_hash(api, snapshot['files'], snapshot['sourceBinding']), original)
        # Same source is a no-op; different commit with the same text is a new bound identity.
        job = self.job()
        self.assertEqual(self.apply(job, source)['activeRevision'], 1)
        self.end(job)
        job = self.job()
        changed = self.apply(job, self.source('b'))
        self.end(job)
        self.assertEqual(changed['activeRevision'], 2)
        self.assertNotEqual(changed['packageHash'], original)
        self.assertEqual(api.inventory(immutable)[2], current['draftHash'])
        # Ordinary Save preserves the runtime/source identity while marking edited text separately.
        draft = self.root / self.ident / 'Workspace/SKILL.md'
        api.atomic(draft, draft.read_bytes() + b'Local authored instruction.\n')
        detail = api.detail(self.db, self.root, self.ident)
        request = dict(id=self.ident, revision=detail['skill']['revision'], draftHash=detail['draftHash'], requestId=str(uuid.uuid4()))
        saved = api.publish(self.db, self.root, request, '/usr/bin/node')
        self.assertTrue(saved['saved'])
        self.assertEqual(api.publish(self.db, self.root, request, '/usr/bin/node'), saved)
        self.assertEqual(saved['source']['active']['commit'], 'b' * 40)
        self.assertNotEqual(saved['source']['active']['importedHash'], saved['draftHash'])
        job = self.job()
        with self.assertRaisesRegex(api.SkillFault, 'local changes'):
            self.apply(job, self.source('c'))
        self.assertIn(b'Local authored', draft.read_bytes())
        self.assertEqual(api.detail(self.db, self.root, self.ident)['skill']['activeHash'], saved['skill']['activeHash'])

    def test_failed_publication_restores_original_and_stale_author_cannot_replace_draft(self):
        before = api.detail(self.db, self.root, self.ident)
        job = self.job()
        with patch.object(api, 'publish', side_effect=OSError('injected storage failure')):
            with self.assertRaises(OSError):
                self.apply(job, self.source('d'))
        self.assertEqual(api.detail(self.db, self.root, self.ident)['draftHash'], before['draftHash'])
        self.assertIsNone(api.detail(self.db, self.root, self.ident)['skill']['activeHash'])
        self.end(job)
        job = self.job()
        draft = self.root / self.ident / 'Workspace/SKILL.md'
        api.atomic(draft, b'Newer author text, preserved.')
        with self.assertRaisesRegex(api.SkillFault, 'changed during preparation'):
            self.apply(job, self.source('e'))
        self.assertEqual(draft.read_bytes(), b'Newer author text, preserved.')

    def test_unresolved_resources_invalid_packages_and_missing_runtime_never_activate(self):
        source, manifest, digest = self.source('f')
        job = self.job()
        manifest['files'][0]['lfs'] = {'materialized': False}
        with self.assertRaisesRegex(api.SkillFault, 'unresolved LFS'):
            self.apply(job, (source, manifest, digest))
        manifest['files'][0].pop('lfs')
        (source / 'Repository/skill/references/guide.md').unlink()
        with self.assertRaisesRegex(api.SkillFault, 'missing from the package'):
            self.apply(job, (source, manifest, digest))
        rea = dict(job, configuration=dict(job['configuration'], recipe='rea'))
        def failed_recipe(*args):
            raise api.SkillFault('Injected runtime prerequisite failure.',409)
        with patch.dict(sys.modules,{'rea_recipe':SimpleNamespace(prepare=failed_recipe)}):
            with self.assertRaisesRegex(api.SkillFault, 'prerequisite failure'):
                self.apply(rea, (source, manifest, digest))
        self.assertIsNone(api.detail(self.db, self.root, self.ident)['skill']['activeHash'])

    def test_corrupt_immutable_manifest_does_not_become_an_update(self):
        source = self.source('1')
        job = self.job()
        published = self.apply(job, source)
        self.end(job)
        path = self.root / self.ident / 'Revisions' / published['packageHash'] / 'revision.json'
        value = json.loads(path.read_text())
        value['sourceBinding']['commit'] = '9' * 40
        api.atomic(path, api.encode(value).encode())
        with self.assertRaisesRegex(api.SkillFault, 'manifest changed'):
            self.apply(self.job(), source)
        self.assertEqual(api.detail(self.db, self.root, self.ident)['skill']['activeRevision'], 1)


if __name__ == '__main__':
    unittest.main()
