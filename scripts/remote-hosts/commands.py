"""Durable command admission, frozen targets and honest local/remote outcomes."""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from catalog import CatalogFault, connection as hosts, fields, identity, integer, now, public as host_public
from transport import RemoteTransport
from actor import encode, still_running
import job_store as jobs
import endpoints
from store import connect
from remote_binding import get as assigned_host
from project_use import acquire


def arguments(value):
    fields(value, ['requestId', 'command'], ['timeoutSeconds']); identity(value['requestId'])
    command = value['command']
    if not isinstance(command, str) or not command.strip() or len(command.encode()) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in command):
        raise CatalogFault('Enter one R4OS command within 4096 UTF-8 bytes.', 400)
    timeout = integer(value.get('timeoutSeconds', 60), 120)
    return {'requestId': value['requestId'], 'command': command, 'timeoutSeconds': timeout}


def target_binding(host): return {k: host[k] for k in ('id', 'endpointRevision', 'credentialRevision', 'trustRevision')}


class Commands:
    def __init__(self, directory, runtime, transport=RemoteTransport):
        self.directory = Path(directory); self.projects = self.directory.parent / 'Projects'; self.runtime = Path(runtime)
        self.transport = transport; self.active = {}

    def metadata(self, actor, call_id, arguments):
        config = actor.verify('get_remote_host', call_id, arguments); fields(arguments)
        frozen = config.get('remoteHostBinding')
        if not frozen:
            return {'available': False, 'reason': config.get('remoteHostAccess', {}).get('reason', 'No Remote Host is assigned to this run.'), 'defaultTarget': 'virtual_machine'}
        with closing(connect(self.projects)) as project_db:
            assigned = assigned_host(project_db, actor.project_id)
        if assigned != frozen.get('id'): raise CatalogFault('The project Remote Host binding changed. Start a new run.', 409)
        with hosts(self.directory) as db:
            current = host_public(db, db.execute('SELECT * FROM hosts WHERE id=?', (frozen['id'],)).fetchone())
        if target_binding(current) != target_binding(frozen): raise CatalogFault('The frozen host endpoint, login or trust changed. Start a new run.', 409)
        check = current.get('lastTest'); ready = (current['hostKey']['state'] == 'trusted' and check and check['status'] == 'success'
                    and all(check.get(k) == current[k] for k in ('endpointRevision', 'credentialRevision', 'trustRevision')))
        return {'available': True, 'host': current, 'hostId': current['id'], 'hostName': current['name'], 'defaultTarget': 'virtual_machine',
                'capabilities': {'commands': bool(ready), 'files': bool(ready)},
                'reason': 'Use only for explicit remote work; Check connection is historical evidence, not current reachability.' if ready else 'Use Check connection in System → Remote Hosts before commands or files.'}

    def admit(self, actor, call_id, raw, tool='run_remote_command'):
        import files
        operation = 'command' if tool == 'run_remote_command' else 'files'
        config = actor.verify(tool, call_id, raw); content = arguments(raw) if operation == 'command' else files.arguments(raw)
        loop = asyncio.get_running_loop(); held = os.dup(actor.fd)
        fingerprint = hashlib.sha256(encode({'sessionId': actor.context['sessionId'], 'operation': operation, 'arguments': raw}).encode()).hexdigest()
        life = None
        try:
            life = acquire(self.projects, actor.project_id)
            with jobs.connection(self.projects, actor.project_id, create=True) as db:
                previous = db.execute('SELECT * FROM jobs WHERE request_id=?', (content['requestId'],)).fetchone()
                if previous:
                    if previous['session_id'] != actor.context['sessionId']: raise CatalogFault('This request belongs to another session.', 403)
                    if previous['fingerprint'] != fingerprint: raise CatalogFault('This request ID belongs to another remote command.')
                    return jobs.public(previous)
                if len(self.active) >= 4: raise CatalogFault('Too many remote commands are active.')
                if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 256: raise CatalogFault('This project’s remote history needs local maintenance.', 503)
                # Keep the project binding stable until the queued job exists.
                # Catalog writers use the other side of the same global lock.
                with closing(connect(self.projects)) as catalog:
                    catalog.execute('BEGIN IMMEDIATE')
                    row = catalog.execute("SELECT pins FROM projects WHERE id=? AND state='ready'", (actor.project_id,)).fetchone()
                    frozen = config.get('remoteHostBinding')
                    if (not row or not isinstance(frozen, dict) or assigned_host(catalog, actor.project_id) != frozen.get('id')
                            or json.loads(row['pins']) != config.get('projectPins')):
                        raise CatalogFault('The run’s frozen project or Remote Host binding changed.', 409)
                    with hosts(self.directory) as host_db:
                        if host_db is None: raise CatalogFault('No Remote Host is configured.', 409)
                        host = host_public(host_db, host_db.execute('SELECT * FROM hosts WHERE id=?', (frozen['id'],)).fetchone())
                        if target_binding(host) != target_binding(frozen): raise CatalogFault('The frozen endpoint, login or trust revision changed.', 409)
                        if host['hostKey']['state'] != 'trusted': raise CatalogFault('Check and trust this host in System → Remote Hosts before executing commands.', 409)
                        checked = host.get('lastTest')
                        if not checked or checked.get('status') != 'success' or any(checked.get(k) != host[k] for k in ('endpointRevision', 'credentialRevision', 'trustRevision')):
                            raise CatalogFault('Confirm R4OS access with Check connection before executing commands on this binding.', 409)
                        mutating = content['command'].strip().upper() != 'VER' if operation == 'command' else content['action'] == 'upload'
                        if mutating and self.unknown_at_endpoint(host):
                            raise CatalogFault('Review the original uncertain remote effect before more commands. An explicit VER diagnostic or permitted file read remains possible.', 409)
                        actor.verify(tool, call_id, raw)
                        job_id = str(uuid.uuid4()); stamp = now()
                        payload = {'schema': 1, 'operation': operation, 'actor': actor.snapshot(tool, call_id), 'host': host,
                                   'deadlineAt': (datetime.now(timezone.utc) + timedelta(seconds=content.get('timeoutSeconds', 120) + 15)).isoformat(),
                                   'adapterRelease': str(Path(__file__).resolve().parents[2])}
                        if operation == 'command': payload.update(command=content['command'], timeoutSeconds=content['timeoutSeconds'])
                        else: payload.update(files=content, **files.prepare(actor, job_id, content))
                        db.execute('BEGIN IMMEDIATE')
                        db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,'queued','accepted',?,NULL,?,?)", (job_id, content['requestId'], fingerprint,
                                   actor.context['sessionId'], actor.context['runId'], host['id'], json.dumps(payload), stamp, stamp))
                        db.commit(); catalog.commit()
                    self.active[job_id] = {'projectId': actor.project_id, 'sessionId': actor.context['sessionId'], 'runId': actor.context['runId'],
                                           'abort': asyncio.Event(), 'life': life, 'fd': held}
                    self.active[job_id]['task'] = loop.create_task(self.run(job_id, payload))
                    life = None; held = None
                return jobs.read(self.projects, actor.project_id, job_id, actor.context['sessionId'])
        finally:
            if life: life.close()
            if held is not None: os.close(held)

    def unknown_at_endpoint(self, host, resolved=None):
        path = self.projects / 'Projects.sqlite'
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            ids = [row[0] for row in db.execute('SELECT id FROM projects')]
        for project_id in ids:
            with jobs.connection(self.projects, project_id) as db:
                if db is None: continue
                for row in db.execute("SELECT payload FROM jobs WHERE state='unknown'"):
                    payload = json.loads(row[0]); target = payload['host']
                    if payload.get('review'): continue
                    if (target['address'], target['port']) == (host['address'], host['port']): return True
                    if resolved is not None:
                        original = payload.get('endpointIdentity')
                        # Legacy uncertainty without a recorded resolved peer
                        # cannot safely be excluded as a DNS alias. Human review
                        # preserves the unknown result while permitting new work.
                        if original is None or endpoints.overlaps(original, resolved): return True
        return False

    async def run(self, job_id, payload):
        entry = self.active[job_id]; pid = entry['projectId']; endpoint = None
        async def watch():
            while not entry['abort'].is_set():
                if not still_running(self.projects, payload['actor']): entry['abort'].set(); return
                await asyncio.sleep(.25)
        monitor = asyncio.create_task(watch())
        try:
            effect = payload['command'].strip().upper() != 'VER' if payload['operation'] == 'command' else payload['files']['action'] == 'upload'
            resolved = await endpoints.resolve(payload['host'])
            endpoint = endpoints.Reservation(self.runtime, resolved, effect)
            if effect and self.unknown_at_endpoint(payload['host'], resolved):
                raise CatalogFault('An original uncertain effect may belong to this resolved endpoint. Review it before new work; no effect was sent.', 409)
            payload = jobs.bind_endpoint(self.projects, pid, job_id, resolved)
            if entry['abort'].is_set(): raise CatalogFault('The original run stopped before command dispatch.', 409)
            # Recheck current target immediately before password materialization.
            from checks import target
            private = target(self.directory, {'hostId': payload['host']['id'], 'binding': target_binding(payload['host'])})
            private['connectAddress'] = resolved['connectAddress']
            if not still_running(self.projects, payload['actor']): raise CatalogFault('The original run ended before dispatch.', 409)
            jobs.update(self.projects, pid, job_id, 'starting', 'client_preparation')
            async with self.transport(private, self.runtime, job_id) as client:
                if payload['operation'] == 'files':
                    import files
                    jobs.update(self.projects, pid, job_id, 'running', 'remote_read')
                    result = await files.perform(client, self.projects, pid, job_id, payload, entry['abort'])
                else:
                    # This durable boundary precedes any possible command send.
                    jobs.update(self.projects, pid, job_id, 'running', 'dispatch_possible')
                    result = await client.execute_complete(payload['command'], payload['timeoutSeconds'], entry['abort'])
            state = ('completed' if payload['operation'] == 'files' else
                     'unknown' if result['transportUncertain'] else 'completed' if result['commandExitCode'] == 0 else 'failed')
            jobs.update(self.projects, pid, job_id, state, 'local_client_ended', result)
        except BaseException as error:
            try:
                original = jobs.read(self.projects, pid, job_id)
                possible = original['phase'] in ('dispatch_possible', 'local_publish_possible')
                jobs.update(self.projects, pid, job_id, 'unknown' if possible else 'failed', 'result_unconfirmed' if possible else 'not_dispatched',
                            {'effectConfirmed': False, 'localClientEndConfirmed': False, 'remoteProcessEndConfirmed': False,
                             **({'transferProgress': original['result']['transferProgress']} if (original.get('result') or {}).get('transferProgress') else {}),
                             'nativeStatus': getattr(error, 'native_code', None),
                             'message': ('The original effect could not be confirmed. It was not repeated.' if possible else
                                         str(error) if isinstance(error, CatalogFault) else
                                         'The operation was not dispatched. Its original request was preserved.')})
            except Exception: pass
        finally:
            monitor.cancel(); await asyncio.gather(monitor, return_exceptions=True)
            if endpoint is not None: endpoint.close()
            os.close(entry['fd']); entry['life'].close(); self.active.pop(job_id, None)
            if payload.get('snapshot'):
                # The receipt retains its hash and original target; terminal
                # reconciliation cannot resend it. No retained secret/source copy.
                (self.projects / pid / 'RemoteHosts/Snapshots' / job_id).unlink(missing_ok=True)

    def read(self, actor, call_id, arguments):
        actor.verify('read_remote_job', call_id, arguments); fields(arguments, optional=['jobId', 'requestId'])
        if set(arguments) == {'jobId'}: return jobs.read(self.projects, actor.project_id, arguments['jobId'], actor.context['sessionId'])
        if set(arguments) != {'requestId'}: raise CatalogFault('Choose the original job ID or request ID.', 400)
        identity(arguments['requestId'])
        with jobs.connection(self.projects, actor.project_id) as db:
            row = db.execute('SELECT * FROM jobs WHERE request_id=?', (arguments['requestId'],)).fetchone() if db else None
            if row is not None and row['session_id'] != actor.context['sessionId']: raise CatalogFault('This request belongs to another session.', 403)
            return jobs.public(row)

    def observe(self, actor, call_id, raw, tool='run_remote_command'):
        actor.verify(tool, call_id, raw)
        if tool == 'remote_files':
            from files import arguments as file_arguments
            file_arguments(raw)
        else: arguments(raw)
        operation = 'files' if tool == 'remote_files' else 'command'
        fingerprint = hashlib.sha256(encode({'sessionId': actor.context['sessionId'], 'operation': operation, 'arguments': raw}).encode()).hexdigest()
        with jobs.connection(self.projects, actor.project_id) as db:
            row = db.execute('SELECT * FROM jobs WHERE request_id=?', (raw['requestId'],)).fetchone() if db else None
            if row is not None and row['session_id'] != actor.context['sessionId']: raise CatalogFault('This request belongs to another session.', 403)
            if row is not None and row['fingerprint'] != fingerprint: raise CatalogFault('The original command arguments changed.', 409)
            return jobs.public(row)

    def stop(self, actor, call_id, arguments):
        actor.verify('stop_remote_job', call_id, arguments); fields(arguments, ['jobId'])
        value = jobs.read(self.projects, actor.project_id, arguments['jobId'], actor.context['sessionId'])
        entry = self.active.get(value['id'])
        if entry: entry['abort'].set()
        return {**value, 'stopRequested': bool(entry), 'remoteProcessEndConfirmed': False}

    def stop_owned(self, actor):
        actor.verify(cleanup=True)
        ids = []
        for job_id, entry in self.active.items():
            if entry['projectId'] == actor.project_id and entry['runId'] == actor.context['runId']:
                entry['abort'].set(); ids.append(job_id)
        return {'jobIds': ids, 'stopRequested': True, 'remoteProcessEndConfirmed': False}

    async def stop_all(self):
        tasks = []
        for entry in tuple(self.active.values()): entry['abort'].set(); tasks.append(entry['task'])
        if tasks:
            try: await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
            except asyncio.TimeoutError:
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
