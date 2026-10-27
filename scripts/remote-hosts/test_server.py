"""Explicit isolated test broker; replaces only the external SSH boundary."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
from host import Host
from transport import private_directory
from test_transport import key


async def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    if root.parent != Path('/tmp') or not root.name.startswith('studio-remote-'): raise SystemExit('An own isolated remote test root is required.')
    runtime = private_directory(root / 'Runtime'); counter = runtime / 'calls.json'
    class FixtureTransport:
        def __init__(self, target, *_):
            if not isinstance(target.get('password'), str) or not target['password']: raise ValueError()
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def check(self):
            count = json.loads(counter.read_text()) if counter.exists() else 0
            counter.write_text(json.dumps(count + 1)); counter.chmod(0o600)
            await asyncio.sleep(.1)
            mode = (runtime / 'outcome').read_text().strip() if (runtime / 'outcome').exists() else 'success'
            if mode == 'auth': return {'status': 'authentication_failed', 'key': key()}
            if mode == 'offline': return {'status': 'offline', 'key': None}
            return {'status': 'success', 'version': '0.0.1', 'kernel': '0.0.2', 'key': key(b'x' if mode == 'changed' else b'k')}
    broker = Host({'directory': str(root / 'RemoteHosts'), 'runtime': str(runtime), 'uid': os.getuid()}, transport=FixtureTransport)
    server = await asyncio.start_unix_server(broker.client, path=runtime / 'host.sock', limit=16385)
    (runtime / 'host.sock').chmod(0o600)
    stopping = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stopping.set)
    print('Own fixture broker ready.', flush=True)
    async with server: await stopping.wait()
    server.close(); await server.wait_closed(); await broker.stop()


if __name__ == '__main__': asyncio.run(main())
