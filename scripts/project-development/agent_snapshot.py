"""Capture through the active agent owner without transferring its workspace lock."""
import asyncio
import json
import os
from pathlib import Path
import socket
import struct

from contracts import DevelopmentFault, encode, identity
from jobs import Jobs, folder
from snapshot import capture


def socket_path(run_id): return Path('/run/r4os-studio-agents') / identity(run_id) / 's.sock'


class AgentSnapshots:
    def __init__(self, worker): self.worker = worker; self.server = None; self.connections = set()

    async def start(self):
        path = socket_path(self.worker.run_id); folder(path.parent)
        if path.exists(): path.unlink()
        self.server = await asyncio.start_unix_server(self.connection, str(path), limit=8193); path.chmod(0o600)

    async def close(self):
        if self.server:
            self.server.close(); await self.server.wait_closed()
            socket_path(self.worker.run_id).unlink(missing_ok=True)
            if self.connections: await asyncio.gather(*self.connections, return_exceptions=True)

    async def connection(self, reader, writer):
        worker = self.worker
        task = asyncio.current_task(); self.connections.add(task)
        try:
            _, uid, _ = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid(): raise DevelopmentFault('Snapshot access denied.', 403)
            value = json.loads(await asyncio.wait_for(reader.readline(), 5))
            if set(value) != {'jobId'}: raise DevelopmentFault('Invalid snapshot request.', 400)
            store = Jobs(worker.manifest['projects'], worker.manifest['r4os'], worker.manifest['projectId'])
            try:
                job = store.get(value['jobId'])
                from authorization import authorize_job
                authorize_job(store, job)
                if job['agentRunId'] != worker.run_id or job['sessionId'] != worker.session_id or worker.stopping:
                    raise DevelopmentFault('The snapshot does not belong to the active agent.')
                # Terminal admission and file tools use these same locks. Existing
                # live terminals can mutate files, so they must finish first.
                async with worker.terminals.lock:
                    async with worker.sandbox.lock:
                        if any(not p.finished.is_set() for p in worker.terminals.processes.values()):
                            raise DevelopmentFault('Finish or stop active terminal processes before building.')
                        run = worker.store.db.execute('SELECT busy,state FROM runs WHERE id=?', (worker.run_id,)).fetchone()
                        if not run or not run['busy'] or run['state'] == 'stopping': raise DevelopmentFault('The agent run is stopping.')
                        source, _ = capture(store, job)
                        store.update(job['id'], source=source, phase='captured')
                result = {'sourceSha256': source['sha256']}
            finally: store.close()
            writer.write((encode({'result': result}) + '\n').encode())
        except DevelopmentFault as error:
            writer.write((encode({'error': str(error), 'code': error.code}) + '\n').encode())
        except Exception:
            writer.write(b'{"error":"The agent snapshot could not be confirmed.","code":409}\n')
        finally:
            try: await writer.drain()
            except Exception: pass
            writer.close()
            self.connections.discard(task)


async def delegated(store, job):
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(socket_path(job['agentRunId']))), 5)
    try:
        writer.write((encode({'jobId': job['id']}) + '\n').encode()); await writer.drain()
        value = json.loads(await asyncio.wait_for(reader.readline(), 30))
        if value.get('error'): raise DevelopmentFault(value['error'], value.get('code', 409))
        source = store.get(job['id'])['source']
        if not source or source['sha256'] != value['result']['sourceSha256']: raise DevelopmentFault('The delegated source receipt is inconsistent.')
        return source, store.root / 'Inputs' / job['id']
    finally:
        writer.close(); await writer.wait_closed()
