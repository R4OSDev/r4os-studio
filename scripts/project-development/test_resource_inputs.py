import unittest
from contracts import DevelopmentFault
from resource_inputs import collect
class ResourceInputs(unittest.TestCase):
    def receipt(self):return {'files':[{'path':'Assets/Icon.ico','bytes':20,'sha256':'a'*64},{'path':'Assets/Scene.rgba','bytes':100,'sha256':'b'*64},{'path':'Assets/Unused.png','bytes':40,'sha256':'c'*64}],'sha256':'d'*64,'manifestSha256':'e'*64}
    def test_sdk_order_names_binary_hashes_unregistered_and_no_embedding_claim(self):
        entry={'icons':['Assets/Icon.ico','Assets/Icon.ico'],'help':None,'resources':['SCENE:Assets/Scene.rgba']};before=repr(entry);value=collect(entry,self.receipt())
        self.assertEqual([e['index'] for e in value['entries']],[0,1,0]);self.assertEqual(value['entries'][2]['sha256'],'b'*64);self.assertEqual(value['unregisteredAssets'],['Assets/Unused.png']);self.assertFalse(value['embeddedVerified']);self.assertEqual(repr(entry),before)
    def test_duplicate_missing_excluded_and_escaping_resources_fail(self):
        for resources in (['SCENE:Assets/Scene.rgba','scene:Assets/Icon.ico'],['MISSING:Assets/Missing.png'],['OUT:../outside'],['OUT:build/excluded.ico']):
            with self.assertRaises(DevelopmentFault):collect({'icons':[],'help':None,'resources':resources},self.receipt())
    def test_legacy_catalog_remains_explicitly_unknown(self):self.assertFalse(collect({},self.receipt())['available'])
if __name__=='__main__':unittest.main()
