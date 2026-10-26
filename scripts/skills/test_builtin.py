"""Shipped knowledge publication, crash-safe identity and user edits/overrides preservation."""
from contextlib import closing
import hashlib,json,shutil,tempfile
from pathlib import Path
import unittest,uuid
import store
from builtin import ensure,BASE,SOURCE
class Builtin(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'Skills';self.db=store.connect(self.root)
 def tearDown(self):self.db.close();self.temp.cleanup()
 def run_ensure(self,base=BASE):return ensure(self.db,self.root,'/usr/bin/node',store,base)
 def test_default_publication_is_complete_and_idempotent_without_overrides(self):
  result=self.run_ensure();self.assertTrue(result['installed']);ident=result['skillId']
  first=store.detail(self.db,self.root,ident);self.assertEqual(first['skill']['activeRevision'],1)
  self.assertIn('references/Updates.txt',[item['path'] for item in first['files']])
  self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],1)
  self.assertFalse(self.run_ensure()['changed']);self.assertEqual(first,store.detail(self.db,self.root,ident))
  self.assertFalse((self.root/'SessionSettings.sqlite').exists())
 def test_user_draft_edit_is_preserved_with_its_published_revision(self):
  ident=self.run_ensure()['skillId'];before=store.detail(self.db,self.root,ident)
  path=self.root/ident/'Workspace/SKILL.md';user=path.read_bytes()+b'\nUser instruction preserved.\n';store.atomic(path,user)
  result=self.run_ensure();self.assertTrue(result['preservedUserChanges']);self.assertEqual(path.read_bytes(),user)
  self.assertEqual(store.detail(self.db,self.root,ident)['skill']['activeHash'],before['skill']['activeHash'])
 def test_user_published_revision_is_preserved(self):
  ident=self.run_ensure()['skillId'];path=self.root/ident/'Workspace/SKILL.md';store.atomic(path,path.read_bytes()+b'\nUser published instruction.\n')
  current=store.detail(self.db,self.root,ident)
  result=store.publish(self.db,self.root,{'id':ident,'revision':current['skill']['revision'],'draftHash':current['draftHash'],'requestId':str(uuid.uuid4())},'/usr/bin/node')
  self.assertTrue(result['saved']);self.assertTrue(self.run_ensure()['preservedUserChanges'])
  self.assertEqual(store.detail(self.db,self.root,ident)['skill']['activeHash'],result['skill']['activeHash'])
 def changed_bundle(self):
  base=Path(self.temp.name)/'bundle';shutil.copytree(BASE,base)
  guide=base/SOURCE/'references/Updates.txt';guide.write_bytes(guide.read_bytes()+b'\nReviewed new release note.\n')
  manifest=json.loads((base/(SOURCE+'.json')).read_text());manifest['version']='0.4.20'
  manifest['files']['references/Updates.txt']=hashlib.sha256(guide.read_bytes()).hexdigest()
  (base/(SOURCE+'.json')).write_text(json.dumps(manifest))
  return base
 def test_untouched_owned_bundle_updates_in_place_without_resetting_catalog(self):
  ident=self.run_ensure()['skillId'];old=store.detail(self.db,self.root,ident)
  result=self.run_ensure(self.changed_bundle());self.assertTrue(result['changed']);self.assertEqual(result['skillId'],ident)
  new=store.detail(self.db,self.root,ident);self.assertEqual(new['skill']['activeRevision'],2)
  self.assertNotEqual(new['skill']['activeHash'],old['skill']['activeHash'])
  self.assertEqual(self.db.execute('SELECT count(*) FROM skills').fetchone()[0],1)
 def test_existing_user_identity_and_corrupt_shipped_file_are_never_overwritten(self):
  manifest=json.loads((BASE/(SOURCE+'.json')).read_text());ident=manifest['id']
  store.create(self.db,self.root,{'id':ident,'name':'User private skill'})
  before=store.detail(self.db,self.root,ident);result=self.run_ensure()
  self.assertTrue(result['preservedUserChanges']);self.assertFalse(result['installed']);self.assertEqual(before,store.detail(self.db,self.root,ident))
  base=self.changed_bundle();(base/SOURCE/'SKILL.md').write_text('Corrupt source')
  with self.assertRaises(store.SkillFault):self.run_ensure(base)
  self.assertEqual(before,store.detail(self.db,self.root,ident))

if __name__=='__main__':unittest.main()
