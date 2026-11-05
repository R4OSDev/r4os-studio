"""Bound admission to existing asyncio thread work, including cancelled clients."""
import asyncio


class ReadWork:
    def __init__(self, fault, limit=4):
        self.fault = fault
        self.limit = limit
        self.pending = set()

    async def run(self, function, *args, **kwargs):
        if len(self.pending) >= self.limit:
            raise self.fault('Local readers are busy. Try this read again shortly.', 429)
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        self.pending.add(task)
        task.add_done_callback(self.finished)
        # Cancelling the socket/request does not cancel the real thread or free
        # its slot early. Its store/locks close in that same thread's finally.
        return await asyncio.shield(task)

    def finished(self, task):
        self.pending.discard(task)
        if not task.cancelled():
            task.exception()  # Consume late failures of an abandoned read.

    async def close(self):
        if self.pending:
            await asyncio.gather(*tuple(self.pending), return_exceptions=True)
