import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from contracts import UnconfirmedGuestEffect
from deskrun import command, DesktopLaunch, NotSubmitted, SSH_EXEC_PREFIX


DEPLOYMENT = {'guestDirectory': r'F:\Build\PBF05AE8\D1FBF342'}


class CommandTest(unittest.TestCase):
    def test_original_missing_world_start_fits_sshd_without_changing_arguments(self):
        arguments = r'--world=F:\Build\PBF05AE8\D1FBF342\ABSENT'
        old = 'DESKRUN /JSON /WAIT:10000 /WAITFRAME "' + DEPLOYMENT['guestDirectory'] + '\\APP.R4X" ' + arguments
        self.assertEqual(len((SSH_EXEC_PREFIX + old).encode()), 130)
        text = command(DEPLOYMENT, arguments, 5000)
        self.assertEqual(len((SSH_EXEC_PREFIX + text).encode()), 118)
        self.assertTrue(text.startswith('DESKRUN /JSON /WAITFRAME '))
        self.assertTrue(text.endswith(' ' + arguments))

    def test_full_terminal_buffer_boundary_uses_utf8_bytes_and_preserves_literal_tail(self):
        for wait in (1000, 5000):
            with self.subTest(wait=wait):
                base = command(DEPLOYMENT, '', wait)
                available = 127 - len((SSH_EXEC_PREFIX + base + ' ').encode())
                arguments = '"ä"  /JSON' + 'x' * (available - len('"ä"  /JSON'.encode()))
                text = command(DEPLOYMENT, arguments, wait)
                self.assertEqual(len((SSH_EXEC_PREFIX + text).encode()), 127)
                self.assertTrue(text.endswith(' ' + arguments))
                with self.assertRaises(NotSubmitted) as rejected:
                    command(DEPLOYMENT, arguments + 'x', wait)
                self.assertTrue(rejected.exception.launch_not_submitted)
                self.assertEqual(rejected.exception.reason_code, 'desktop_arguments_too_long')
                if wait < 5000: self.assertIn('/WAIT:1000 ', text)


class UnconfirmedTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_identity_remains_unknown_and_never_repeats_submission(self):
        # Even a matching stderr string is not a trusted no-start receipt.
        response = {'stdout': b'', 'stderr': b'exec request failed on channel 0\r\n',
            'sshExitCode': 255, 'transportUncertain': True}
        with tempfile.TemporaryDirectory() as root:
            owner = SimpleNamespace(work=Path(root), store=SimpleNamespace(update=AsyncMock()), job={'id': 'original'})
            launch = DesktopLaunch(owner, object(), DEPLOYMENT, None)
            with patch.object(launch, 'guard'), patch('deskrun.exchange', AsyncMock(return_value=response)) as send:
                with self.assertRaises(UnconfirmedGuestEffect):
                    await launch.query(command(DEPLOYMENT, '', 5000), 10, starting=True)
                self.assertEqual(send.await_count, 1)
            self.assertIsNone(launch.key)
            self.assertTrue((Path(root) / 'deskrun-1.transport.json').is_file())


if __name__ == '__main__': unittest.main()

class BudgetTest(unittest.TestCase):
    def test_same_canonical_bytes_at_unicode_and_wait_boundaries(self):
        from deskrun import launch_budget
        for wait in (99,999,1000,4999,5000):
            baseline=launch_budget(DEPLOYMENT,'',wait);capacity=baseline['argumentCapacityBytes']
            arguments='ä🙂'+'x'*(capacity-len('ä🙂'.encode()))
            value=launch_budget(DEPLOYMENT,arguments,wait)
            self.assertEqual(value['commandBytes'],112);self.assertEqual(value['wrapperBytes'],15)
            self.assertEqual(value['remainingArgumentBytes'],0);self.assertTrue(value['withinLimit'])
            self.assertEqual(len(command(DEPLOYMENT,arguments,wait).encode()),value['commandBytes'])
            self.assertEqual(launch_budget(DEPLOYMENT,arguments+'ä',wait)['overByBytes'],2)
            with self.assertRaises(NotSubmitted) as failure:command(DEPLOYMENT,arguments+'ä',wait)
            self.assertNotIn(arguments,str(failure.exception));self.assertTrue(failure.exception.launch_not_submitted)
        self.assertGreater(launch_budget(DEPLOYMENT,'',999)['fixedBytes'],launch_budget(DEPLOYMENT,'',99)['fixedBytes'])
    def test_missing_or_changed_binding_has_no_safe_guessed_capacity(self):
        import copy,json,uuid
        from desktop_budget import selected
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);vm={'id':str(uuid.uuid4()),'revision':'r','imageId':'image','imageSha256':'a'*64}
            project={'revision':2,'vmId':vm['id'],'pins':{}}
            target={'vmId':vm['id'],'vmRevision':'r','imageId':'image','imageSha256':'a'*64,'bootId':'own-boot'}
            deployment={**DEPLOYMENT,'id':'deployment','projectId':'project','jobId':'deploy-job','role':'desktop','pins':{},'target':target}
            store=SimpleNamespace(project=project,id='project',projects=root,get=lambda _:{'state':'completed','projectRevision':2},settings=lambda:{'revision':1,'arguments':'ä','timeoutSeconds':5})
            self.assertFalse(selected(store,deployment,vm)['available'])
            path=root/'.studio/development/Boots'/ (vm['id']+'.json');path.parent.mkdir(parents=True)
            from lease import birth
            import os
            path.write_text(json.dumps({'schema':1,'connected':True,'bootId':'own-boot','vmId':vm['id'],'vmRevision':vm['revision'],'imageId':vm['imageId'],'imageSha256':vm['imageSha256'],'pid':os.getpid(),'birth':birth(os.getpid())}))
            value=selected(store,deployment,vm);self.assertTrue(value['available']);self.assertEqual(value['saved']['argumentBytes'],2)
            for key in ('bootId','vmRevision','imageSha256'):
                changed=copy.deepcopy(deployment);changed['target'][key]='foreign'
                self.assertEqual(selected(store,changed,vm)['available'],False)
