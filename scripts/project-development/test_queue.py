import asyncio,unittest,uuid
from lease import VmLease
from queue_lease import reserve
from contracts import DevelopmentFault
from store import connect
import test_jobs

class QueueTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_projects_serialize_without_repeating_effects_and_stop_closes_waiting(self):
        f=test_jobs.JobsTest();f.setUp();vm=str(uuid.uuid4())
        try:
            with connect(f.root) as db:db.execute('UPDATE projects SET vm_id=? WHERE id=?',(vm,f.id))
            f.store.project['vmId']=vm;job,_=f.store.admit('build',f.input());job=f.store.update(job['id'],'running',binding={'id':vm})
            first=VmLease(f.root,vm,{'kind':'qa'});first.__enter__()
            async def free():await asyncio.sleep(.05);first.__exit__(None,None,None)
            task=asyncio.create_task(free())
            async with reserve(f.store,job,{'kind':'job'},timeout=1) as second:self.assertNotEqual(first.id,second.id)
            await task;self.assertEqual(f.store.get(job['id'])['phase'],'waiting_for_vm')
            with VmLease(f.root,vm,{'kind':'qa'}):
                with self.assertRaises(DevelopmentFault):
                    async with reserve(f.store,job,{'kind':'job'},timeout=0):self.fail('Busy VM admitted')
                f.store.update(job['id'],'stopping')
                with self.assertRaises(DevelopmentFault):
                    async with reserve(f.store,job,{'kind':'job'},timeout=1):self.fail('Stopped job admitted')
        finally:f.tearDown()
