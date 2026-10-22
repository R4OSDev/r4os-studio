import json,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import AsyncMock,patch
from lease import VmLease
from layout import save
from forwards import cleanup

class ForwardsTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_stale_owned_forward_is_removed_and_its_secret_retired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);vm=str(uuid.uuid4());other=str(uuid.uuid4());scope={'kind':'access'}
            with VmLease(root,vm,scope) as old:old_id=old.id
            records=old.root/'Forwards';records.mkdir();file=records/(old_id+'.json');save(file,{'vmId':vm,'leaseId':old_id,'port':23456,'scope':scope,'state':'open'})
            unrelated=records/(str(uuid.uuid4())+'.json');save(unrelated,{'vmId':other,'state':'open'})
            runtime=root/'auth'/old_id;runtime.mkdir(parents=True);(runtime/'password').write_text('private-fixture')
            call=AsyncMock(side_effect=[{'vm':{'state':'running'}},{'configured':True}])
            with VmLease(root,vm,scope) as current,patch('forwards.RUNTIME',root/'auth'),patch('forwards.vm_call',call):
                self.assertEqual(await cleanup(current),[old_id]);self.assertEqual(await cleanup(current),[])
            self.assertFalse(runtime.exists());self.assertEqual(json.loads(file.read_text())['state'],'closed');self.assertEqual(json.loads(unrelated.read_text())['state'],'open');self.assertEqual(call.await_args_list[-1].args[1],'forward_close');self.assertEqual(call.await_args_list[-1].kwargs,{'port':23456})
