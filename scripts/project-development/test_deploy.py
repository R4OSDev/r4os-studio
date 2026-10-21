import asyncio
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock

from contracts import DevelopmentFault, digest
from sftp import remote, publish_file


class TransferTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_readback_bytes_prevent_a_publication_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); source = root / 'APP.R4X'; source.write_bytes(b'expected-module')
            ssh = SimpleNamespace(runtime=root)
            async def corrupt_readback(transport, guest, local, **kwargs):
                Path(local).write_bytes(b'corrupt-module'); return True
            with patch('sftp.batch', new=AsyncMock(return_value=True)), patch('sftp.download', side_effect=corrupt_readback):
                with self.assertRaisesRegex(DevelopmentFault, 'Guest bytes do not match'):
                    await publish_file(ssh, source, '/C/P1234567/D1234567/APP.R4X', digest(source))
            self.assertFalse(list(root.glob('verify-*')))

    async def test_guest_paths_and_changed_local_bytes_fail_before_transfer(self):
        for path in ('/C/../SYSTEM/APP.R4X', '/D/APP.R4X', '/C/a/APP.R4X', '/C/P1234567/APP.R4X\nrm /C/x'):
            with self.assertRaises(DevelopmentFault): remote(path)
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'APP.R4X'; source.write_bytes(b'modified')
            with patch('sftp.batch', new=AsyncMock()) as transfer:
                with self.assertRaises(DevelopmentFault):
                    await publish_file(SimpleNamespace(runtime=Path(root)), source, '/C/P1234567/APP.R4X', '0' * 64)
                transfer.assert_not_called()


if __name__ == '__main__': unittest.main()
