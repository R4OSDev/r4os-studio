import asyncio
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from image_instructions import compose,ALIAS
from image_recipes import target
import test_image_import as image_import_tests

class Workflow(unittest.TestCase):
    def config(self):return {'engine':{'profile':'studio-tools-v11'},'owner':{'type':'project'},'nativeImageGeneration':True,'permissions':{'studio.list_generated_images':True,'studio.import_generated_image':True,'studio.write_file':True,'studio.read_file':True}}
    def test_complete_workflow_uses_real_tools_evidence_and_frozen_rights(self):
        text=compose(self.config())
        for word in ('image_gen.imagegen','studio_list_generated_images','studio_import_generated_image','RESOURCE=NAME:','ICON=<path>','resourceInventory','Verified in guest',ALIAS,'straight RGBA32','cannot authorize Roadmap cleanup'):
            self.assertIn(word,text)
        self.assertLess(len(text),7000)
    def test_disabled_unknown_legacy_skill_and_write_denied_remain_explicit(self):
        value=self.config();value['nativeImageGeneration']=False;value['imageGenerationCapability']={'reason':'Account policy unavailable.'};self.assertIn('Account policy unavailable',compose(value));self.assertIn('must not be regenerated automatically',compose(value))
        value['permissions']['studio.write_file']=False;self.assertIn('do not bypass disabled import/write rights',compose(value))
        value['engine']['profile']='studio-tools-v10';self.assertIn('original tool profile',compose(value));self.assertNotIn('studio_import_generated_image',compose(value))
        value['engine']['profile']='studio-skill-tools-v4';value['owner']['type']='skill';self.assertIn('no app project importer',compose(value));self.assertNotIn('RESOURCE=NAME:',compose(value))
    def test_only_explicit_virtual_sdk_root_routes_to_companion(self):
        self.assertEqual(target({'root':'sdk','path':ALIAS+'/images.zig'}),['images.zig']);self.assertIsNone(target({'root':'workspace','path':ALIAS+'/images.zig'}));self.assertIsNone(target({'root':'sdk','path':'r4os/ico.zig'}))

class Companion(unittest.IsolatedAsyncioTestCase):
    setUp=image_import_tests.Imports.setUp
    open=image_import_tests.Imports.open
    asyncTearDown=image_import_tests.Imports.asyncTearDown
    async def test_actual_read_list_search_are_readonly_and_need_no_sdk_execution(self):
        worker=self.worker;worker.manifest['r4os']=str(self.root/'R4OS');sdk='a'*40;worker.config['projectPins']={'sdk':{'revision':sdk},'contract':{'revision':'b'*40}}
        root=self.root/'R4OS/SDK'/sdk;root.mkdir(parents=True)
        with patch.object(worker.sandbox,'prepare',side_effect=AssertionError('Recipe read must not launch compilers')):
            result=await worker.sandbox.file('read_file',{'root':'sdk','path':ALIAS+'/images.zig','startLine':1,'maxLines':30});self.assertTrue(result['success']);self.assertIn('pub fn own',result['output']);self.assertTrue(result['companion']['readonly'])
            original=Path(__file__).resolve().parents[2]/'shared/r4os/image-recipes/images.zig';self.assertEqual(result['sha256'],hashlib.sha256(original.read_bytes()).hexdigest())
            listing=await worker.sandbox.file('list_directory',{'root':'sdk','path':ALIAS});self.assertIn('README.txt',listing['output'])
            found=await worker.sandbox.file('search',{'root':'sdk','path':ALIAS,'query':'moduleResourceRead'});self.assertTrue(found['success']);self.assertIn('images.zig',found['output'])
            denied=await worker.sandbox.file('write_file',{'root':'sdk','path':ALIAS+'/README.txt','content':'must not write','expectedSha256':None});self.assertEqual(denied['error'],'readOnly')
            self.assertFalse((root/ALIAS).exists())
            (root/ALIAS).mkdir();blocked=await worker.sandbox.file('read_file',{'root':'sdk','path':ALIAS+'/README.txt'});self.assertEqual(blocked['error'],'conflict')

if __name__=='__main__':unittest.main()
