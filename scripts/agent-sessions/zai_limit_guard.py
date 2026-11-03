"""Limit future model calls; never replay or cancel confirmed tool effects."""
import asyncio
from zai_limits import state


async def watch(worker):
    try:
        while not worker.done.is_set() and not worker.stopping:
            blocked=await asyncio.to_thread(state,worker.manifest['providers'],worker.config['apiProvider'],worker.config['model'])
            if blocked:
                worker.api_runtime.subscription_reason=blocked['reason']
                await worker.api_runtime.block_subscription()
                return
            await asyncio.sleep(.5)
    except asyncio.CancelledError:pass
    except Exception:pass  # Unknown monitoring alone is not an inference denial.
