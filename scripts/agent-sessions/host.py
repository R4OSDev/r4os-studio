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
from protocol import release_protocol, supported_profiles, validate_release
from store import ProjectFault
from owner import binding, owners, skills_root

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
        self.lock = asyncio.Lock(); self.active = {}; self.unbound = set(); self.connections = set()

    def store(self, ident, kind='project'): return SessionStore(self.config['projects'], self.config['r4os'], ident, kind)

    async def active_unit(self, run_id):
        state = await systemctl('show', UNIT.format(identity(run_id)), '--property=ActiveState', '--value')
        return state in ('active', 'activating', 'deactivating', 'reloading')

    def metadata(self, path):
        if path.resolve(strict=True) != path.absolute(): raise ValueError('Invalid worker record.')
        value = json.loads(path.read_text())
        binding(value)
        for key in ('runId', 'sessionId', 'providerId'): identity(value[key])
        if path.parent.name != value['runId'] or value['schema'] != 1: raise ValueError('Invalid worker record.')
        for key in ('projects', 'r4os', 'providers'):
            if value[key] != self.config[key]: raise ValueError('Invalid worker storage binding.')
        validate_release(value)
        return value

    async def recover(self):
        # Never restart a queued/model/tool operation on coordinator or host boot.
        manifests = {}
        for path in self.root.glob('*/worker.json'):
            try:
                value = self.metadata(path); manifests[value['runId']] = value
            except Exception: continue  # Preserve corrupt records; active units below fail closed.
        from store import connect
        from contextlib import closing
        with closing(connect(Path(self.config['projects']))) as db:
            projects = [r['id'] for r in db.execute("SELECT id FROM projects WHERE state='ready'")]
        registered = [('project', ident) for ident in projects] + owners(self.config['projects'])
        for kind, project_id in registered:
            # Inspect registered session databases only; no discovery/creation in
            # foreign project folders or pre-session legacy workspaces.
            root = skills_root(self.config['projects']) if kind == 'skill' else Path(self.config['projects'])
            if not (root / project_id / 'Sessions/Sessions.sqlite').is_file(): continue
            try: store = self.store(project_id, kind)
            except Exception: continue
            try:
                for row in store.db.execute('SELECT * FROM runs WHERE busy=1').fetchall():
                    value = manifests.get(row['id'])
                    if value and binding(value) == (kind, project_id) and value['sessionId'] == row['session_id'] and await self.active_unit(row['id']):
                        self.active[row['id']] = value
                    else:
                        transition(store, row['id'], 'unknown', 'The run ended without a confirmed result; tool effects were not repeated.')
                        from worker import reconcile_items
                        reconcile_items(store, row['id'])
                # Repair stale pending cards from earlier compatible releases
                # using confirmed receipts, without replaying any tool operation.
                finished = set()
                for row in store.db.execute('SELECT i.run_id,i.payload FROM items i JOIN runs r ON r.id=i.run_id WHERE r.busy=0'):
                    if json.loads(row['payload']).get('status') in ('pending', 'running'): finished.add(row['run_id'])
                for run_id in finished:
                    from worker import reconcile_items
                    reconcile_items(store, run_id, get_run(store, run_id)['state'])
            finally: store.close()
        await self.check_unbound()

    async def check_unbound(self):
        raw = await systemctl('list-units', '--all', '--state=active,activating,deactivating,reloading', '--plain', '--no-legend', '--no-pager', 'r4os-studio-agent@*.service')
        units = set()
        for line in raw.splitlines():
            match = re.match(r'^r4os-studio-agent@([a-f0-9-]{36})\.service\s', line.strip())
            if match: units.add(identity(match[1]))
        self.unbound = units - set(self.active)

    async def refresh(self):
        for run_id, meta in list(self.active.items()):
            if await self.active_unit(run_id): continue
            kind, ident = binding(meta)
            try: store = self.store(ident, kind)
            except ProjectFault as error:
                if error.code != 404: raise
                self.active.pop(run_id, None); continue
            try:
                row = get_run(store, run_id)
                if row['busy']:
                    transition(store, run_id, 'unknown', 'The run service stopped without a confirmed result.')
                    from worker import reconcile_items
                    reconcile_items(store, run_id)
                self.active.pop(run_id, None)
            finally: store.close()
        await self.check_unbound()

    async def handle(self, request):
        op = request.get('operation')
        if op == 'capabilities': return {'enabled': not bool(self.unbound), 'protocol': 1, 'projectDeletionLocks': 1, 'projectInstructions': 1, 'vmStartTools': 1, 'skillSessions': 1, 'skillAuthorTools': 1, 'globalSkills': 1, 'skillScripts': 1, 'nativeWebSearch': 1, 'roadmapSettings': 1, 'roadmapTools': 1, 'maxActiveRuns': self.config.get('maxActiveRuns', 2), 'version': json.loads((Path(__file__).resolve().parents[2] / 'shared/version.json').read_text())['version']}
        if op == 'cancel_provider':
            provider_id = identity(request['providerId'])
            async with self.lock:
                await self.refresh()
                if self.unbound: raise ProjectFault('Reconcile unbound agent workers before disconnecting a provider.', 503)
                for run_id, meta in list(self.active.items()):
                    if meta['providerId'] == provider_id:
                        kind, ident = binding(meta)
                        await self.stop(ident, meta['sessionId'], run_id, kind)
            return {'stopped': True}
        kind, project_id = binding(request)
        session_id = identity(request['sessionId'])
        if op == 'events':
            store = self.store(project_id, kind)
            try: return events(store, session_id, request.get('after', 0))
            finally: store.close()
        if op == 'stop_run':
            async with self.lock: return await self.stop(project_id, session_id, identity(request['runId']), kind)
        if op == 'start_run':
            async with self.lock:
                await self.refresh()
                if self.unbound: raise ProjectFault('An agent worker has no confirmed binding. Restore host support before starting another run.', 503)
                store = self.store(project_id, kind)
                try:
                    # Duplicate requests are admitted idempotently even at capacity.
                    previous = store.db.execute('SELECT id FROM runs WHERE request_id=?', (request['input'].get('requestId'),)).fetchone()
                    if not previous and request['input'].get('roadmapSettings') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if kind != 'project' or not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/roadmap_access.py').is_file():
                            raise ProjectFault('This worker release cannot provide the saved Roadmap setting.', 503)
                    if not previous and request['input'].get('nativeWebSearch') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/web_search.py').is_file():
                            raise ProjectFault('This worker release cannot provide the saved Web search setting.', 503)
                    if not previous and request['input'].get('skillSelection') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/skill_application.py').is_file():
                            raise ProjectFault('This worker release cannot apply the saved session skill choices.', 503)
                        if request['input'].get('skillScripts') == 1 and not (target / 'scripts/agent-sessions/skill_scripts.py').is_file():
                            raise ProjectFault('This worker release cannot provide frozen skill script resources.', 503)
                    if not previous and len(self.active) >= self.config.get('maxActiveRuns', 2):
                        raise ProjectFault('The host is already running its maximum number of agent runs.')
                    run, fresh = admit(store, session_id, request['input'], self.config['providers'])
                    if not fresh: return run
                    try:
                        release = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not release.is_relative_to('/opt/r4os-studio/releases'): raise ProjectFault('Invalid agent worker release.', 503)
                        release_protocol(release)
                        if not (release / 'scripts/agent-sessions/instructions.py').is_file():
                            raise ProjectFault('This worker release cannot apply project instructions.', 503)
                        if store.get(session_id)['engine']['profile'] not in supported_profiles(release): raise ProjectFault('This conversation needs a newer Studio release; its native thread was preserved.', 409)
                        info = json.loads((release / 'release.json').read_text())
                        meta = {'schema': 1, 'runId': run['id'], 'ownerType': kind, 'ownerId': project_id, 'sessionId': session_id,
                                'providerId': store.get(session_id)['providerId'], 'projects': self.config['projects'],
                                'r4os': self.config['r4os'], 'providers': self.config['providers'],
                                'releaseRoot': str(release), 'release': info['id'], 'version': info['version']}
                        if kind == 'project': meta['projectId'] = project_id
                        parent = directory(self.root / run['id']); write_json(parent / 'worker.json', meta)
                        self.active[run['id']] = meta
                        await systemctl('start', '--no-block', UNIT.format(run['id']))
                    except Exception:
                        # A lost systemctl response may still have started a unit.
                        # Keep its durable admission while it is alive or unknown.
                        try: alive = await self.active_unit(run['id'])
                        except Exception: alive = True
                        if not alive:
                            self.active.pop(run['id'], None)
                            transition(store, run['id'], 'failed', 'The agent run service could not start.')
                        raise
                    return run
                finally: store.close()
        raise ProjectFault('Unsupported agent coordinator operation.', 400)

    async def stop(self, project_id, session_id, run_id, kind='project'):
        store = self.store(project_id, kind)
        try:
            store.row(session_id)
            row = get_run(store, run_id)
            if row['session_id'] != session_id: raise ProjectFault('Run not found.', 404)
            if row['busy'] or await self.active_unit(run_id):
                transition(store, run_id, 'stopping')
                await systemctl('stop', UNIT.format(run_id))
                row = get_run(store, run_id)
                if row['busy']: transition(store, run_id, 'interrupted', 'Run stopped.')
            self.active.pop(run_id, None)
            self.unbound.discard(run_id)
            return store.run_present(get_run(store, run_id))
        finally: store.close()

    async def connection(self, reader, writer):
        task = asyncio.current_task(); self.connections.add(task)
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
            self.connections.discard(task)


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
    replacement = None
    async def maintain():
        nonlocal replacement
        while not stopped.is_set():
            try:
                async with host.lock:
                    await host.refresh()
                    target = Path('/opt/r4os-studio/current').resolve(strict=True)
                    if not host.active and not host.unbound and target != Path(__file__).resolve().parents[2]:
                        release_protocol(target)
                        script = target / 'scripts/agent-sessions/host.py'
                        if not target.is_relative_to('/opt/r4os-studio/releases') or script.stat().st_uid != 0 or script.stat().st_mode & 0o022:
                            raise ValueError('Invalid coordinator release.')
                        replacement = script; stopped.set()
            except Exception: pass  # Preserve current workers and retry, never infer a new job.
            try: await asyncio.wait_for(stopped.wait(), 2)
            except asyncio.TimeoutError: pass
    monitor = asyncio.create_task(maintain())
    async with server: await stopped.wait()
    monitor.cancel(); await asyncio.gather(monitor, return_exceptions=True)
    if host.connections:
        try: await asyncio.wait_for(asyncio.gather(*host.connections, return_exceptions=True), 25)
        except asyncio.TimeoutError: pass
    if replacement: os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(replacement)])


if __name__ == '__main__': asyncio.run(main())
