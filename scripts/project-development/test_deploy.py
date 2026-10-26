import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock, Mock
import uuid

from contracts import DevelopmentFault, digest
from sftp import remote, publish_file


class TransferTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_image_and_new_components_reach_deployment_worker(self):
        from host import Host
        from vm_worker import Deployment
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); project_id, vm_id, job_id = [str(uuid.uuid4()) for _ in range(3)]
            vm = {'id':vm_id,'name':'New image','revision':str(uuid.uuid4()),'imageId':'99.99.99-full','imageSha256':'f'*64,'networkEnabled':True}
            path = root / 'R4OS/Instances' / vm_id / 'vm.json'; path.parent.mkdir(parents=True); path.write_text(json.dumps(vm))
            store = SimpleNamespace(id=project_id, r4os=root/'R4OS', projects=root,
                project={'id':project_id,'language':'Rust','template':'desktop','pins':{'sdk':{'revision':'e'*40}},'vmId':vm_id,'revision':1},
                settings=lambda:{'revision':1}, db=Mock(), admit=Mock(return_value=({'id':job_id},False)), close=Mock(),
                root=root/'Development', evidence=lambda _id:root, artifact=Mock(return_value={}), update=Mock())
            store.db.execute.return_value.fetchone.return_value = None
            host = Host({'projects':str(root),'r4os':str(root/'R4OS')})
            host.store = lambda _id:store; host.refresh = AsyncMock(); host.access.public = Mock(return_value={'available':True,'ready':False,'reason':None})
            self.assertTrue(host.options(store)['deploy']['available'])
            result = await host.handle({'operation':'deploy','projectId':project_id,'input':{'requestId':str(uuid.uuid4())}})
            self.assertEqual(result['id'], job_id); store.admit.assert_called_once()
            job = {'id':job_id,'binding':vm,'artifactId':str(uuid.uuid4()),'pins':store.project['pins'],'projectRevision':1,'kind':'deploy'}
            class HelperReached(Exception): pass
            @asynccontextmanager
            async def reserved(*args,**kwargs):yield SimpleNamespace(id=str(uuid.uuid4()),token='fixture')
            with patch('queue_lease.reserve',reserved), patch('vm_worker.guard'), patch('vm_worker.vm_call',new=AsyncMock(return_value={'vm':{'state':'running'}})), patch('exchange.require_tree'), patch('vm_worker.prepare_helper', new=AsyncMock(side_effect=HelperReached)) as helper:
                with self.assertRaises(HelperReached): await Deployment(store,job).run()
                helper.assert_awaited_once()

    async def test_different_readback_bytes_prevent_a_publication_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root); source = root / 'APP.R4X'; source.write_bytes(b'expected-module')
            ssh = SimpleNamespace(runtime=root)
            async def corrupt_readback(transport, lines, **kwargs):
                import shlex
                destination=shlex.split(lines[1])[-1]
                Path(destination).write_bytes(b'corrupt-module'); return True
            with patch('sftp.batch', side_effect=corrupt_readback):
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
