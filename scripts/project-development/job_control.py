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
        if value.get('error'): raise DevelopmentFault(value['error'], value.get('code', 409))
        return value['result']
    except (OSError, ValueError, asyncio.TimeoutError): raise UnconfirmedGuestEffect('The execution action receipt was lost. The action was not replayed.') from None
    finally: writer.close(); await writer.wait_closed()


class Mailbox:
    def __init__(self, job_id):
        self.id = identity(job_id); self.queue = asyncio.Queue(maxsize=4); self.server = None; self.peers = set()

    async def open(self):
        path = endpoint(self.id); folder(path.parent)
        if path.exists(): path.unlink()
        self.server = await asyncio.start_unix_server(self.connection, str(path), limit=16385); path.chmod(0o600)

    async def connection(self, reader, writer):
        self.peers.add(writer)
        try:
            _, uid, _ = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, os.getuid()): raise DevelopmentFault('Execution control denied.', 403)
            raw = await asyncio.wait_for(reader.readline(), 5)
            if not raw or len(raw) > 16384: raise DevelopmentFault('Execution action exceeds its limit.', 400)
            message = json.loads(raw)
            if not isinstance(message, dict): raise DevelopmentFault('Invalid execution action.', 400)
            future = asyncio.get_running_loop().create_future()
            # A client may time out while the queued action is still pending.
            # Consume a later exception without replaying that action.
            future.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
            try: self.queue.put_nowait((message, future))
            except asyncio.QueueFull: raise DevelopmentFault('The execution action queue is full.') from None
            result = await asyncio.wait_for(asyncio.shield(future), 18)
            writer.write((encode({'result': result}) + '\n').encode())
        except DevelopmentFault as error: writer.write((encode({'error': str(error), 'code': error.code}) + '\n').encode())
        except Exception: writer.write(b'{"error":"The execution action result is unconfirmed.","code":503}\n')
        finally:
            try: await writer.drain()
            except Exception: pass
            writer.close(); await writer.wait_closed(); self.peers.discard(writer)

    async def close(self):
        if self.server: self.server.close(); await self.server.wait_closed()
        for peer in tuple(self.peers): peer.close()
        while not self.queue.empty():
            _, future = self.queue.get_nowait()
            if not future.done(): future.set_exception(DevelopmentFault('The execution ended before admitting this action.'))
        endpoint(self.id).unlink(missing_ok=True)
