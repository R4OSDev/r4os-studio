#!/usr/bin/env python3
"""Private fixed-operation coordinator. It never replays a queued effect."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import struct

from contracts import APP, ACTIVE, DevelopmentFault, LIMITS, encode, identity, protocol
from jobs import Jobs, folder
from layout import save
from profiles import eligible
from store import ProjectFault, connect

UNIT = 'r4os-studio-development@{}.service'


async def systemctl(*args):
    process = await asyncio.create_subprocess_exec('/usr/bin/systemctl', '--no-ask-password', *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    output, _ = await asyncio.wait_for(process.communicate(), 20)
    if process.returncode: raise DevelopmentFault('The development worker service could not be controlled.', 503)
    return output.decode().strip()


class Host:
    def __init__(self, config):
        self.config = config; self.lock = asyncio.Lock(); self.active = {}; self.unbound = set(); self.connections = set()
        self.root = folder(Path(config['projects']) / '.studio/development')

    def store(self, project_id): return Jobs(self.config['projects'], self.config['r4os'], project_id)

    async def alive(self, job_id):
        return await systemctl('show', UNIT.format(identity(job_id)), '--property=ActiveState', '--value') in ('active', 'activating', 'deactivating', 'reloading')

    def metadata(self, path):
        if path.resolve(strict=True) != path.absolute(): raise ValueError('Invalid worker metadata.')
        value = json.loads(path.read_text())
        for key in ('jobId', 'projectId'): identity(value[key])
        if value['schema'] != 1 or path.parent.name != value['jobId']: raise ValueError('Invalid worker identity.')
        if any(value[k] != self.config[k] for k in ('projects', 'r4os')): raise ValueError('Invalid worker storage.')
        return value

    async def recover(self):
        manifests = {}
        for path in self.root.glob('*/worker.json'):
            try:
                value = self.metadata(path); manifests[value['jobId']] = value
            except Exception: continue
        db = connect(Path(self.config['projects']))
        try: projects = [row[0] for row in db.execute("SELECT id FROM projects WHERE state='ready'")]
        finally: db.close()
        for project_id in projects:
            if not (Path(self.config['projects']) / project_id / 'Development/Development.sqlite').is_file(): continue
            store = self.store(project_id)
            try:
                for row in store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchall():
                    meta = manifests.get(row['id'])
                    if meta and meta['projectId'] == project_id and await self.alive(row['id']): self.active[row['id']] = meta
                    else: store.update(row['id'], 'unknown', phase='recovery', error='The job ended without a confirmed result. It was not restarted.')
            finally: store.close()
        await self.refresh()

    async def refresh(self):
        for job_id, meta in list(self.active.items()):
            if await self.alive(job_id): continue
            store = self.store(meta['projectId'])
            try: store.update(job_id, 'unknown', phase='recovery', error='The worker ended without a confirmed result. It was not restarted.')
            finally: store.close()
            self.active.pop(job_id, None)
        raw = await systemctl('list-units', '--all', '--state=active,activating,deactivating,reloading', '--plain', '--no-legend', '--no-pager', 'r4os-studio-development@*.service')
        units = set()
        for line in raw.splitlines():
            match = re.match(r'^r4os-studio-development@([a-f0-9-]{36})\.service\s', line.strip())
            if match: units.add(identity(match[1]))
        self.unbound = units - set(self.active)

    def options(self, store):
        from contracts import hash_value
        project = store.project; image = None; vm = None
        if project['vmId']:
            try:
                path = store.r4os / 'Instances' / identity(project['vmId']) / 'vm.json'
                if path.resolve(strict=True) != path: raise ValueError()
                vm = json.loads(path.read_text()); image = {'id': vm['imageId'], 'sha256': vm['imageSha256']}
            except (OSError, ValueError, KeyError): pass
        match = eligible(project, image)
        unavailable = {'available': False, 'reason': 'Guest development access is not configured.'}
        if project['vmId'] and not image:
            unavailable = {'available': False, 'reason': 'Assigned VM metadata is unavailable. Development host maintenance is required.'}
        return {'revision': hash_value({'project': project['revision'], 'settings': store.settings()['revision'], 'image': image}),
            'build': {'available': True}, 'deploy': unavailable, 'execute': unavailable,
            'capture': unavailable, 'input': unavailable, 'profileId': match['profileId'],
            'qualification': match, 'assignedVm': {'id': vm['id'], 'name': vm['name'],
                'imageId': image['id'], 'ready': False} if vm and image else None}

    async def handle(self, request, peer_pid=None):
        op = request.get('operation')
        if op == 'capabilities' and set(request) == {'operation'}:
            return {'enabled': not self.unbound, 'protocol': 1, 'maxActiveJobs': LIMITS['activeHostJobs'],
                    'version': json.loads((APP / 'shared/version.json').read_text())['version']}
        allowed = {'operation', 'projectId'}
        if op in ('read_job', 'stop_job', 'artifact'): allowed.add('id')
        if op == 'read_job': allowed.add('offset')
        if op == 'build': allowed.update(('input', 'owner'))
        if set(request) - allowed or op not in ('options', 'settings', 'jobs', 'read_job', 'stop_job', 'artifact', 'build'):
            raise DevelopmentFault('Unsupported development coordinator operation.', 400)
        store = self.store(identity(request['projectId']))
        try:
            if op == 'options': return self.options(store)
            if op == 'settings': return store.settings()
            if op == 'jobs': return store.list()
            if op == 'read_job': return store.page(request['id'], request.get('offset', 0))
            if op == 'artifact': return store.artifact(request['id'])
            async with self.lock:
                await self.refresh()
                if self.unbound: raise DevelopmentFault('A development worker has no confirmed binding. Restore host support.', 503)
                if op == 'stop_job':
                    job_id = identity(request['id']); job = store.get(job_id)
                    if job['state'] in ACTIVE or await self.alive(job_id):
                        store.update(job_id, 'stopping', phase='stopping')
                        await systemctl('stop', UNIT.format(job_id))
                        store.update(job_id, 'interrupted', phase='stopped', error='Job stopped.')
                    self.active.pop(job_id, None); return store.get(job_id)
                previous = store.db.execute('SELECT id FROM jobs WHERE request_id=?', (request['input'].get('requestId'),)).fetchone()
                owner = request.get('owner')
                if owner is not None:
                    if not isinstance(owner, dict) or set(owner) != {'sessionId', 'agentRunId'}:
                        raise DevelopmentFault('Invalid delegated build owner.', 400)
                    for value in owner.values(): identity(value)
                    path = store.projects / store.id / 'Sessions/Sessions.sqlite'
                    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid delegated session data.')
                    db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
                    try:
                        row = db.execute('SELECT busy,state,worker,config FROM runs WHERE id=? AND session_id=?',
                            (owner['agentRunId'], owner['sessionId'])).fetchone()
                    finally: db.close()
                    if not row or not row[0] or row[1] == 'stopping' or json.loads(row[2] or '{}').get('pid') != peer_pid:
                        raise DevelopmentFault('This build is not delegated by the active workspace owner.', 403)
                    if not json.loads(row[3])['permissions'].get('studio.build_project', False):
                        raise DevelopmentFault('Project builds are disabled for this agent run.', 403)
                if not previous:
                    if len(self.active) >= LIMITS['activeHostJobs']: raise DevelopmentFault('The host is already running its maximum number of development jobs.')
                    if not owner and store.agent_busy(): raise DevelopmentFault('The workspace is owned by an active agent. Request a build through that agent or wait for it to finish.')
                job, fresh = store.admit('build', request['input'], owner)
                if not fresh: return job
                try:
                    release = Path('/opt/r4os-studio/current').resolve(strict=True)
                    if not release.is_relative_to('/opt/r4os-studio/releases'): raise DevelopmentFault('Invalid development release.', 503)
                    protocol(release); info = json.loads((release / 'release.json').read_text())
                    meta = {'schema': 1, 'jobId': job['id'], 'projectId': store.id,
                        'projects': self.config['projects'], 'r4os': self.config['r4os'],
                        'releaseRoot': str(release), 'release': info['id'], 'version': info['version']}
                    save(folder(self.root / job['id']) / 'worker.json', meta)
                    self.active[job['id']] = meta
                    await systemctl('start', '--no-block', UNIT.format(job['id']))
                except BaseException:
                    try: alive = await self.alive(job['id'])
                    except Exception: alive = True
                    if not alive:
                        store.update(job['id'], 'failed', phase='failed', error='The development worker could not start.')
                        self.active.pop(job['id'], None)
                    raise
                return job
        finally: store.close()

    async def connection(self, reader, writer):
        task = asyncio.current_task(); self.connections.add(task)
        try:
            sock = writer.get_extra_info('socket')
            peer_pid, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, self.config['uid']): raise DevelopmentFault('Development coordinator access denied.', 403)
            raw = await asyncio.wait_for(reader.readline(), 10)
            if len(raw) > 131072: raise DevelopmentFault('Development request too large.', 400)
            result = await self.handle(json.loads(raw), peer_pid); writer.write((encode({'result': result}) + '\n').encode())
        except (DevelopmentFault, ProjectFault) as error:
            writer.write((encode({'error': str(error), 'code': error.code}) + '\n').encode())
        except Exception:
            writer.write(b'{"error":"The development coordinator is unavailable.","code":503}\n')
        finally:
            try: await writer.drain()
            except Exception: pass
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass
            self.connections.discard(task)


async def main():
    os.umask(0o077); protocol(APP)
    config = json.loads(Path('/etc/r4os-studio-development/config.json').read_text())
    if os.getuid() != config['uid']: raise SystemExit('Run the coordinator as its configured service user.')
    host = Host(config); await host.recover(); path = folder('/run/r4os-studio-development') / 'host.sock'
    if path.exists(): path.unlink()
    server = await asyncio.start_unix_server(host.connection, path=str(path), limit=131073); path.chmod(0o600)
    stopped = asyncio.Event(); loop = asyncio.get_running_loop(); replacement = None
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stopped.set)
    async def maintain():
        nonlocal replacement
        while not stopped.is_set():
            try:
                async with host.lock:
                    await host.refresh(); release = Path('/opt/r4os-studio/current').resolve(strict=True)
                    if not host.active and not host.unbound and release != APP:
                        protocol(release); script = release / 'scripts/project-development/host.py'
                        if not release.is_relative_to('/opt/r4os-studio/releases') or script.stat().st_uid != 0 or script.stat().st_mode & 0o022: raise ValueError()
                        replacement = script; stopped.set()
            except Exception: pass
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
