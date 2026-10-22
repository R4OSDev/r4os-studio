import unittest
from contracts import APP, DevelopmentFault, generation, identity, protocol, relative
from profiles import runner, eligible
from access import guest_version


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

    def test_runner_does_not_gate_image_sdk_or_compiler_revisions(self):
        for language in ('Zig', 'C', 'Rust'):
            project = {'language':language, 'template':'terminal', 'pins':{'sdk':{'revision':'f'*40},'zig':{'binarySha256':'f'*64}}}
            for image in ({'id':'0.84.46-full','sha256':'a'*64}, {'id':'99.99.99-full','sha256':'b'*64}):
                self.assertTrue(eligible(project,image)['available'])
            self.assertFalse(eligible({**project,'template':'driver'},image)['available'])
            self.assertFalse(eligible(project,None)['available'])
        self.assertNotIn('image', runner())

    def test_guest_readiness_reads_versions_without_a_release_or_kernel_list(self):
        for release, kernel in [('0.84.46', '0.1.330'), ('99.99.99', '9.8.7')]:
            value = guest_version({'exitCode':0,'output':'R4OS Release '+release+'\nKernel active '+kernel})
            self.assertEqual(value, {'release':release,'kernel':kernel})
        for result in ({'exitCode':0,'output':'another guest'}, {'exitCode':1,'output':'R4OS Release 99.99.99\nKernel active 9.8.7'}):
            with self.assertRaises(DevelopmentFault): guest_version(result)


if __name__ == '__main__': unittest.main()
