import unittest
from scratch import retire
from contracts import DevelopmentFault
import test_recovery
class ScratchTest(unittest.TestCase):
    def test_only_verified_success_scratch_is_discarded_without_following_links(self):
        f=test_recovery.RecoveryTest();f.setUp()
        try:
            job,artifact=f.build();work=f.store.root/'Work'/job['id'];work.mkdir(parents=True);(work/'own-temp').write_text('generated')
            self.assertFalse(retire(f.store,job));self.assertTrue(work.exists())
            result=__import__('recovery').local(f.store,job);(work/'outside').symlink_to(f.store.workspace,target_is_directory=True)
            self.assertTrue(retire(f.store,result));self.assertFalse(work.exists());self.assertTrue((f.store.workspace/'main.zig').exists());self.assertTrue((artifact/'TEST.R4X').exists());self.assertTrue((f.store.root/'Inputs'/job['id']/'main.zig').exists())
        finally:f.tearDown()
