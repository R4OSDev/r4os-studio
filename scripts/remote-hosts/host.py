#!/usr/bin/env python3
"""Unprivileged peer-checked Unix broker. Only a saved-target VER check for now."""
import asyncio
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import sys

from catalog import CatalogFault, fields, identity, now, regular
import checks
from transport import RemoteTransport, private_directory, transport_profile


class Host:
    def __init__(self, config, transport=RemoteTransport):
        self.config = config; self.directory = Path(config['directory']); self.runtime = Path(config['runtime'])
        self.transport = transport; self.active = {}; self.connections = set()
        self.accepting = True

    def capabilities(self):
        transport_profile()
        version = json.loads((Path(__file__).resolve().parents[2] / 'shared/version.json').read_text())['version']
        return {'protocol': 1, 'test': True, 'commands': False, 'files': False, 'version': version, 'activeChecks': len(self.active)}

    async def request(self, request):
        fields(request, ['protocol', 'operation'], ['hostId', 'input', 'requestId'])
        if type(request['protocol']) is not int or request['protocol'] != 1: raise CatalogFault('Unsupported remote broker protocol.', 400)
        op = request['operation']
        if op == 'capabilities': fields(request, ['protocol', 'operation']); return self.capabilities()
        if op == 'prepare_adoption':
            fields(request, ['protocol', 'operation'])
            if self.active: return {'ready': False, 'activeChecks': len(self.active)}
            self.accepting = False; return {'ready': True, 'activeChecks': 0}
        if op == 'read':
            fields(request, ['protocol', 'operation', 'hostId', 'requestId'])
            return checks.status(self.directory, request['hostId'], request['requestId'])
        if op != 'test': raise CatalogFault('Unsupported remote broker operation.', 400)
        if not self.accepting: raise CatalogFault('Remote host support is adopting an update. Retry the original request.', 503)
        fields(request, ['protocol', 'operation', 'hostId', 'input'])
        identity(request['hostId']); fields(request['input'], ['requestId', 'revision']); identity(request['input']['requestId'])
        self.capabilities()
        if len(self.active) >= 4 and request['input']['requestId'] not in self.active: raise CatalogFault('Too many connection checks are active.')
        value = checks.begin(self.directory, request['hostId'], request['input'])
        if value['phase'] == 'accepted' and value['requestId'] not in self.active:
            task = asyncio.create_task(self.run(value)); self.active[value['requestId']] = task
        return checks.status(self.directory, value['hostId'], value['requestId'])

    async def run(self, value):
        try:
            target = checks.target(self.directory, value)
            value = {**value, 'phase': 'connecting', 'updatedAt': now()}; checks.save(checks.path_for(self.directory, value['requestId']), value)
            async with self.transport(target, self.runtime, value['requestId']) as client: outcome = await client.check()
            checks.finish(self.directory, value, outcome)
        except BaseException:
            # Even cancellation or a lost result write must not replay SSH. A
            # committed catalog receipt wins over an incomplete sidecar journal.
            try:
                original = checks.status(self.directory, value['hostId'], value['requestId'])
                if original['phase'] != 'complete': checks.save(checks.path_for(self.directory, value['requestId']), {**value, 'phase': 'unknown', 'updatedAt': now(), 'message': 'The original connection check could not be confirmed. It was not repeated.'})
            except Exception: pass  # Preserve all original evidence for local maintenance.
        finally: self.active.pop(value['requestId'], None)

    async def client(self, reader, writer):
        if len(self.connections) >= 16: writer.close(); return
        self.connections.add(writer)
        try:
            peer = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i', peer)[1] != self.config['uid']: raise CatalogFault('Remote broker peer is not authorized.', 403)
            raw = await asyncio.wait_for(reader.readline(), 5)
            if not raw.endswith(b'\n') or len(raw) > 16384: raise CatalogFault('Invalid remote broker frame.', 400)
            try: result = await self.request(json.loads(raw)); reply = {'result': result}
            except CatalogFault as error: reply = {'error': str(error), 'code': error.code}
            except Exception: reply = {'error': 'Remote host support could not confirm the request. Preserve the original request ID.', 'code': 503}
            writer.write(json.dumps(reply, ensure_ascii=True).encode() + b'\n'); await writer.drain()
        except Exception: pass
        finally: self.connections.discard(writer); writer.close(); await writer.wait_closed()

    async def stop(self):
        tasks = tuple(self.active.values())
        for task in tasks: task.cancel()
        if tasks: await asyncio.gather(*tasks, return_exceptions=True)


@contextmanager
def runtime_lock(runtime):
    path = runtime / '.broker.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        regular(path)
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise CatalogFault('The original remote broker still owns this runtime.', 503) from None
        yield
    finally: os.close(fd)


async def main():
    os.umask(0o077); path = Path(sys.argv[1]).absolute()
    if path.resolve(strict=True) != path or path.stat().st_uid != 0 or path.stat().st_mode & 0o022 or path.stat().st_size > 16384:
        raise SystemExit('A fixed root-owned local remote broker configuration is required.')
    config = json.loads(path.read_text()); fields(config, ['schema', 'uid', 'directory', 'runtime'])
    if config['schema'] != 1 or config['uid'] != os.geteuid() or os.geteuid() == 0: raise SystemExit('Run the remote broker as its configured unprivileged user.')
    with runtime_lock(private_directory(config['runtime'])): await serve(config)


async def serve(config):
    runtime = private_directory(config['runtime']); private_directory(runtime / 'auth')
    checks.recover(config['directory'])
    # Only original UUID auth directories from the previous stopped broker.
    for entry in (runtime / 'auth').iterdir(): identity(entry.name); private_directory(entry); shutil.rmtree(entry)
    socket_path = runtime / 'host.sock'
    if socket_path.exists() or socket_path.is_symlink():
        if not socket_path.is_socket() or socket_path.is_symlink(): raise SystemExit('Unexpected remote runtime socket; preserve it for maintenance.')
        socket_path.unlink()
    host = Host(config); server = await asyncio.start_unix_server(host.client, path=socket_path, limit=16385); socket_path.chmod(0o600)
    stopping = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stopping.set)
    async with server: await stopping.wait()
    server.close(); await server.wait_closed(); await host.stop()


if __name__ == '__main__': asyncio.run(main())
