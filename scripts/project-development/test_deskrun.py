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
