import copy
import unittest
from contracts import APP, DevelopmentFault, generation, identity, protocol, relative
from profiles import catalog, eligible


class Contracts(unittest.TestCase):
    def test_generations_and_paths_preserve_native_precision_and_scope(self):
        self.assertEqual(generation('18446744073709551615'), '18446744073709551615')
        for value in ('0', '01', '-1', '18446744073709551616', 9007199254740993):
            with self.assertRaises(DevelopmentFault): generation(value)
        self.assertEqual(relative('Resources/Test.dat'), 'Resources/Test.dat')
        for value in ('/etc/passwd', '../Sessions', 'C:\\TEMP\\A', 'a//b', 'a/./b', 'file\nname'):
            with self.assertRaises(DevelopmentFault): relative(value)
        with self.assertRaises(DevelopmentFault): identity('chosen-host-path')
        self.assertEqual(protocol(APP)['guestProtocol'], 1)

    def test_image_and_role_adapter_do_not_gate_sdk_or_compiler_revisions(self):
        profile = catalog()['profiles'][0];c = profile['components'];image = profile['image']
        for language in ('Zig', 'C', 'Rust'):
            pins = copy.deepcopy(c['pinSets'][language])
            project = {'language':language, 'template':'terminal', 'pins':pins}
            self.assertTrue(eligible(project,image)['available'])
            changed = copy.deepcopy(project);changed['pins']['contract']['revision'] = '0'*40
            self.assertTrue(eligible(changed,image)['available'])
            changed = copy.deepcopy(project);changed['pins']['zig']['binarySha256'] = '0'*64
            self.assertTrue(eligible(changed,image)['available'])
            self.assertFalse(eligible(project,{**image,'sha256':'0'*64})['available'])
            self.assertFalse(eligible(project,{'id':'0.84.47-full','sha256':image['sha256']})['available'])
            self.assertFalse(eligible({**project,'template':'driver'},image)['available'])


if __name__ == '__main__': unittest.main()
