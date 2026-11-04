"""Artifact boundaries and real namespace failures must preserve prior data."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import uuid
import managed_download
import rea_recipe

spec=importlib.util.spec_from_file_location('managed_recipe_test_store',Path(__file__).with_name('store.py'))
api=importlib.util.module_from_spec(spec);sys.modules[spec.name]=api;spec.loader.exec_module(api)


class Artifacts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.canary=self.root/'outside-canary';self.canary.write_bytes(b'preserved original')

    def tearDown(self):self.temp.cleanup()

    def archive(self,name,link=None):
        archive=self.root/'node.tar.xz'
        with tarfile.open(archive,'w:xz') as tar:
            item=tarfile.TarInfo(name)
            if link is None:
                data=b'not an executable';item.size=len(data);tar.addfile(item,io.BytesIO(data))
            else:
                item.type=tarfile.SYMTYPE;item.linkname=link;tar.addfile(item)
        return archive

    def test_archive_traversal_and_escaping_link_do_not_touch_other_files(self):
        for index,(name,link) in enumerate([('../outside-canary',None),('node/bin/node','../../../outside-canary')]):
            archive=self.archive(name,link);stage=self.root/str(index);stage.mkdir()
            with patch.object(managed_download,'download',return_value=archive):
                with self.assertRaises(Exception):managed_download.install_node(api,{'url':'https://nodejs.org/official','cache':str(archive),'sha256':'a'*64},stage/'Node')
            self.assertEqual(self.canary.read_bytes(),b'preserved original')
            self.assertFalse((stage/'Node').exists())

    def test_changed_or_linked_cached_artifact_is_preserved_and_rejected(self):
        cache=self.root/'cache';cache.write_bytes(b'corrupt original artifact')
        with self.assertRaises(api.SkillFault):managed_download.download(api,'https://nodejs.org/official',cache,1024,'a'*64)
        self.assertEqual(cache.read_bytes(),b'corrupt original artifact')
        cache.unlink();cache.symlink_to(self.canary)
        with self.assertRaises(ValueError):managed_download.download(api,'https://nodejs.org/official',cache,1024)
        self.assertEqual(self.canary.read_bytes(),b'preserved original')

    def source(self,resolved=None):
        source=self.root/'Source';repository=source/'Repository';repository.mkdir(parents=True)
        (repository/'package.json').write_text('{"name":"rea-agents","version":"6.8.0"}')
        (repository/'.npmrc').write_text('engine-strict=true\n');(repository/'.nvmrc').write_text('24.22.1\n')
        lock={'packages':{} if resolved is None else {'node_modules/adversary':{'resolved':resolved,'integrity':'sha512-fixture'}}}
        (repository/'package-lock.json').write_text(json.dumps(lock));(source/'manifest.json').write_text('{"schema":1}')
        return source

    def job(self):
        return dict(skillId=str(uuid.uuid4()),requestId=str(uuid.uuid4()),configuration=dict(repository='https://github.com/morluto/rea',skillPath='.agents/skills/reverse-engineer-anything'))

    def test_dependency_lock_cannot_select_credential_url_or_foreign_registry(self):
        source=self.source('https://token@registry.npmjs.org/package.tgz');job=self.job();progress=[]
        with patch.object(rea_recipe,'node_plan',side_effect=AssertionError('Preflight must precede network')):
            with self.assertRaisesRegex(api.SkillFault,'unreviewed external source'):
                rea_recipe.prepare(api,self.root/'Skills',job['skillId'],job,source,{'commit':'a'*40},lambda **v:progress.append(v))
        self.assertEqual(progress,[])

    @unittest.skipIf(os.getuid()==0,'Exercise the real namespace as the service owner.')
    def test_wrong_managed_node_never_falls_back_to_host_node(self):
        source=self.source();job=self.job();skills=self.root/'Skills'
        before=skills/job['skillId']/'Workspace';before.mkdir(parents=True);(before/'SKILL.md').write_bytes(b'old active bytes preserved')
        plan=dict(version='v24.22.1',sha256='b'*64,architecture='x64')
        def wrong_node(api_value,plan_value,target):
            (target/'bin').mkdir(parents=True)
            (target/'bin/node').write_bytes(b'foreign architecture executable\x00')
            os.chmod(target/'bin/node',0o500)
            return dict(path='Node/bin/node',sha256=hashlib.sha256((target/'bin/node').read_bytes()).hexdigest(),version='v24.22.1')
        with patch.object(rea_recipe,'node_plan',return_value=plan),patch.object(rea_recipe,'install_node',side_effect=wrong_node):
            with self.assertRaisesRegex(api.SkillFault,'node-version phase failed'):
                rea_recipe.prepare(api,skills,job['skillId'],job,source,{'commit':'a'*40},lambda **_:None)
        self.assertEqual((before/'SKILL.md').read_bytes(),b'old active bytes preserved')
        work=skills/job['skillId']/'Builds'/job['requestId']
        self.assertFalse((work/'dependencies.log').exists())
        self.assertNotEqual(json.loads((work/'node-version-receipt.json').read_text())['exit'],0)


if __name__=='__main__':unittest.main()
