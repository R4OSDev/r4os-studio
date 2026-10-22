"""Bounded VM serialization, without replaying any guest effect."""
import asyncio
from contextlib import asynccontextmanager
from contracts import DevelopmentFault
from lease import VmLease, VmBusy


@asynccontextmanager
async def reserve(store, job, scope, timeout=180):
    from vm_worker import guard
    deadline = asyncio.get_running_loop().time() + timeout
    lease = None
    try:
        while True:
            guard(store, job)
            lease = VmLease(store.projects, job['binding']['id'], scope)
            try: lease.__enter__(); break
            except VmBusy:
                lease = None
                if asyncio.get_running_loop().time() >= deadline: raise DevelopmentFault('The assigned VM remained busy. No guest action was started.')
                store.update(job['id'], phase='waiting_for_vm'); await asyncio.sleep(.25)
        yield lease
    finally:
        if lease: lease.__exit__(None, None, None)
