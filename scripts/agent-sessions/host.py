#!/usr/bin/env python3
"""Unprivileged fixed-operation agent coordinator. Runs live in separate units."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import sys

from profile import write_json, directory
from session_store import SessionStore, identity, encode
from run_store import admit, get_run, transition, events
from store import ProjectFault

UNIT = 'r4os-studio-agent@{}.service'


async def systemctl(*args):
    proc = await asyncio.create_subprocess_exec('/usr/bin/systemctl', '--no-ask-password', *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    output, _ = await asyncio.wait_for(proc.communicate(), 20)
    if proc.returncode: raise ProjectFault('The agent run service could not be controlled.', 503)
    return output.decode().strip()


class Host:
    def __init__(self, config):
        self.config = config
        self.root = directory(Path(config['projects']) / '.studio/agents')
        self.lock = asyncio.Lock(); self.active = {}

    def store(self, project_id): return SessionStore(self.config['projects'], self.config['r4os'], project_id)

    async def active_unit(self, run_id):
        state = await systemctl('show', UNIT.format(identity(run_id)), '--property=ActiveState', '--value')
        return state in ('active', 'activating', 'deactivating', 'reloading')

    async def recover(self):
        # Never start an inference job simply because the host/coordinator booted.
        for path in self.root.glob('*/worker.json'):
            try:
                if path.resolve(strict=True) != path.absolute(): continue
                value = json.loads(path.read_text()); store = self.store(value['projectId'])
                try:
                    row = get_run(store, value['runId'])
                    if row['busy']:
                        if await self.active_unit(row['id']): self.active[row['id']] = value
                        else: transition(store, row['id'], 'unknown', 'The host stopped before a confirmed run result; no tools were repeated.')
                finally: store.close()
            except Exception: continue

    async def refresh(self):
        for run_id, meta in list(self.active.items()):
            store = self.store(meta['projectId'])
            try:
                row = get_run(store, run_id)
                if not row['busy']: self.active.pop(run_id, None)
                elif not await self.active_unit(run_id):
                    transition(store, run_id, 'unknown', 'The run service stopped without a confirmed result.'); self.active.pop(run_id, None)
            finally: store.close()

    async def handle(self, request):
        op = request.get('operation')
        if op == 'capabilities': return {'enabled': True, 'protocol': 1, 'maxActiveRuns': self.config.get('maxActiveRuns', 2)}
        if op == 'cancel_provider':
            provider_id = identity(request['providerId'])
            async with self.lock:
                for run_id, meta in list(self.active.items()):
                    if meta['providerId'] == provider_id:
                        await self.stop(meta['projectId'], meta['sessionId'], run_id)
            return {'stopped': True}
        project_id = identity(request['projectId'])
        session_id = identity(request['sessionId'])
        if op == 'events':
            store = self.store(project_id)
            try: return events(store, session_id, request.get('after', 0))
            finally: store.close()
        if op == 'stop_run':
            async with self.lock: return await self.stop(project_id, session_id, identity(request['runId']))
        if op == 'start_run':
            async with self.lock:
                await self.refresh()
                store = self.store(project_id)
                try:
                    # Duplicate requests are admitted idempotently even at capacity.
                    previous = store.db.execute('SELECT id FROM runs WHERE request_id=?', (request['input'].get('requestId'),)).fetchone()
                    if not previous and len(self.active) >= self.config.get('maxActiveRuns', 2):
                        raise ProjectFault('The host is already running its maximum number of agent runs.')
                    run, fresh = admit(store, session_id, request['input'], self.config['providers'])
                    if not fresh: return run
                    try:
                        release = Path('/opt/r4os-studio/current').resolve(strict=True)
                        if not release.is_relative_to('/opt/r4os-studio/releases'): raise ProjectFault('Invalid agent worker release.', 503)
                        info = json.loads((release / 'release.json').read_text())
                        meta = {'schema': 1, 'runId': run['id'], 'projectId': project_id, 'sessionId': session_id,
                                'providerId': store.get(session_id)['providerId'], 'projects': self.config['projects'],
                                'r4os': self.config['r4os'], 'providers': self.config['providers'],
                                'releaseRoot': str(release), 'release': info['id'], 'version': info['version']}
                        parent = directory(self.root / run['id']); write_json(parent / 'worker.json', meta)
                        self.active[run['id']] = meta
                        await systemctl('start', '--no-block', UNIT.format(run['id']))
                    except Exception:
                        self.active.pop(run['id'], None)
                        transition(store, run['id'], 'failed', 'The agent run service could not start.'); raise
                    return run
                finally: store.close()
        raise ProjectFault('Unsupported agent coordinator operation.', 400)

    async def stop(self, project_id, session_id, run_id):
        store = self.store(project_id)
        try:
            row = get_run(store, run_id)
            if row['session_id'] != session_id: raise ProjectFault('Run not found.', 404)
            if row['busy']:
                transition(store, run_id, 'stopping')
                await systemctl('stop', UNIT.format(run_id))
                row = get_run(store, run_id)
                if row['busy']: transition(store, run_id, 'interrupted', 'Run stopped.')
            self.active.pop(run_id, None)
            return store.run_present(get_run(store, run_id))
        finally: store.close()

    async def connection(self, reader, writer):
        try:
            sock = writer.get_extra_info('socket')
            _, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, self.config['uid']): raise ProjectFault('Agent coordinator access denied.', 403)
            raw = await asyncio.wait_for(reader.readline(), 10)
            if len(raw) > 131072: raise ProjectFault('Agent request too large.', 400)
            result = await self.handle(json.loads(raw))
            writer.write((encode({'result': result}) + '\n').encode())
        except ProjectFault as e:
            writer.write((encode({'error': str(e), 'code': e.code}) + '\n').encode())
        except Exception:
            writer.write(b'{"error":"The agent coordinator is unavailable.","code":503}\n')
        finally:
            try: await writer.drain()
            except Exception: pass
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass


async def main():
    os.umask(0o077)
    config = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    if os.getuid() != config['uid']: raise SystemExit('Run the coordinator as its configured service user.')
    host = Host(config); await host.recover()
    runtime = directory('/run/r4os-studio-agents')
    path = runtime / 'host.sock'
    if path.exists(): path.unlink()
    server = await asyncio.start_unix_server(host.connection, path=str(path), limit=131073)
    path.chmod(0o600)
    stopped = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stopped.set)
    async with server: await stopped.wait()


if __name__ == '__main__': asyncio.run(main())
