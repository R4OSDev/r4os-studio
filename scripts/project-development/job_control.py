"""A private, bounded action mailbox for the one live execution worker."""
import asyncio
import json
import os
from pathlib import Path
import socket
import struct
from contracts import DevelopmentFault, UnconfirmedGuestEffect, encode, identity
from jobs import folder


def endpoint(job_id): return folder('/run/r4os-studio-development/Jobs') / identity(job_id) / 'c.sock'


async def call(job_id, message):
    path = endpoint(job_id)
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(path), limit=2097153), 3)
    except (OSError, asyncio.TimeoutError): raise DevelopmentFault('This execution has no active control channel.') from None
    try:
        writer.write((encode(message) + '\n').encode()); await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), 20)
        value = json.loads(raw)
        if value.get('error'):
            if value.get('uncertain'): raise UnconfirmedGuestEffect(value['error'])
            raise DevelopmentFault(value['error'], value.get('code', 409))
        return value['result']
    except (OSError, ValueError, asyncio.TimeoutError): raise UnconfirmedGuestEffect('The execution action receipt was lost. The action was not replayed.') from None
    finally:
        writer.close()
        try: await asyncio.wait_for(writer.wait_closed(), .5)
        except Exception: pass


class Mailbox:
    def __init__(self, job_id):
        self.id = identity(job_id); self.queue = asyncio.Queue(maxsize=4); self.server = None
        self.peers = set(); self.pending = set(); self.connections = set(); self.closing = False

    async def open(self):
        if self.closing: raise DevelopmentFault('This execution mailbox is closing.')
        path = endpoint(self.id); folder(path.parent)
        if path.exists(): path.unlink()
        self.server = await asyncio.start_unix_server(self.connection, str(path), limit=16385); path.chmod(0o600)

    async def next(self, timeout, wake):
        """Wake promptly for actions/Stop, retaining a raced queue delivery."""
        if self.closing: raise DevelopmentFault('This execution mailbox is closing.')
        queued = asyncio.create_task(self.queue.get())
        signaled = asyncio.create_task(wake.wait())
        try:
            await asyncio.wait((queued, signaled), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (queued, signaled):
                if not task.done(): task.cancel()
            await asyncio.gather(queued, signaled, return_exceptions=True)
        if wake.is_set(): wake.clear()
        return queued.result() if not queued.cancelled() and queued.exception() is None else None

    def settled(self, future):
        self.pending.discard(future)
        if not future.cancelled(): future.exception()

    async def connection(self, reader, writer):
        task = asyncio.current_task(); self.connections.add(task); self.peers.add(writer)
        def reply(value):
            try: writer.write((encode(value) + '\n').encode())
            except (ConnectionError, RuntimeError): pass  # A closed peer does not authorize replay.
        try:
            if self.closing: raise DevelopmentFault('The execution ended before admitting this action.')
            _, uid, _ = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, os.getuid()): raise DevelopmentFault('Execution control denied.', 403)
            raw = await asyncio.wait_for(reader.readline(), 5)
            if not raw or len(raw) > 16384: raise DevelopmentFault('Execution action exceeds its limit.', 400)
            message = json.loads(raw)
            if not isinstance(message, dict): raise DevelopmentFault('Invalid execution action.', 400)
            if self.closing: raise DevelopmentFault('The execution ended before admitting this action.')
            future = asyncio.get_running_loop().create_future()
            # Track dequeued actions too. A disconnected peer never authorizes
            # replay, and a later original result still needs to be consumed.
            self.pending.add(future); future.add_done_callback(self.settled)
            try: self.queue.put_nowait((message, future))
            except asyncio.QueueFull:
                future.cancel()
                raise DevelopmentFault('The execution action queue is full.') from None
            result = await asyncio.wait_for(asyncio.shield(future), 18)
            reply({'result': result})
        except DevelopmentFault as error:
            reply({'error': str(error), 'code': error.code, 'uncertain': bool(getattr(error, 'uncertain', False))})
        except Exception:
            reply({'error':'The execution action result is unconfirmed.','code':503})
        finally:
            try:
                try: await asyncio.wait_for(writer.drain(), .5)
                except Exception: pass
            finally:
                writer.close()
                try: await asyncio.wait_for(writer.wait_closed(), .5)
                except Exception: pass
                finally:
                    self.peers.discard(writer); self.connections.discard(task)

    async def close(self):
        self.closing = True
        if self.server: self.server.close()
        # Queued requests were not admitted. A dequeued request may already
        # have affected the guest and must never become a successful closure.
        while not self.queue.empty():
            _, future = self.queue.get_nowait()
            if not future.done(): future.set_exception(DevelopmentFault('The execution ended before admitting this action.'))
        for future in tuple(self.pending):
            if not future.done():
                future.set_exception(UnconfirmedGuestEffect('The original execution action ended without a confirmed result. Inspect its saved receipt; do not repeat it.'))
        # Allow bounded delivery of those original failures, then close peers
        # before waiting for the server: Python waits for all connections.
        tasks = {task for task in self.connections if task is not asyncio.current_task() and not task.done()}
        if tasks: await asyncio.wait(tasks, timeout=.25)
        for peer in tuple(self.peers): peer.close()
        if self.server:
            try: await asyncio.wait_for(self.server.wait_closed(), 1)
            except asyncio.TimeoutError:
                for peer in tuple(self.peers): peer.transport.abort()
        tasks = {task for task in self.connections if task is not asyncio.current_task() and not task.done()}
        for task in tasks: task.cancel()
        if tasks: await asyncio.wait(tasks, timeout=1)
        endpoint(self.id).unlink(missing_ok=True)
