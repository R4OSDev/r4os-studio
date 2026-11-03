#!/usr/bin/env python3
"""Explicit, recoverable whole-project SDK cutover. Never starts a guest or agent."""
import argparse
import asyncio
import base64
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import uuid

from layout import folder, save, sync
from store import connect, public, ProjectFault
from project_use import acquire, project_id
from project_maintenance import require_idle
import sdk_migration_guard as guard
import project_pins

sys.path[:0] = [str(Path(__file__).parents[1] / 'components'), str(Path(__file__).parents[1] / 'project-development')]
import sdk_provision
from sdk_sets import profile_revision
from jobs import Jobs


def projects(root):
    db = connect(root)
    try:
        if db.execute("SELECT 1 FROM projects WHERE state!='ready'").fetchone():
            raise ProjectFault('Finish original project creation/deletion before SDK migration.', 409)
        return [public(row, db) for row in db.execute('SELECT * FROM projects ORDER BY id')]
    finally:
        db.close()


def component_status():
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(15); client.connect('/run/r4os-studio-components/control.sock')
        client.sendall(b'{"command":"status"}\n'); raw = b''
        while b'\n' not in raw:
            block = client.recv(65536)
            if not block or len(raw) + len(block) > 4 * 1024**2:
                raise ProjectFault('Component status could not be confirmed.', 503)
            raw += block
    value = json.loads(raw.split(b'\n')[0])
    if 'error' in value:
        raise ProjectFault(value['error'], 503)
    return value['status']


def gate(path, request_id, operation):
    value = {'schema': 1, 'operation': operation, 'requestId': request_id}
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True); folder(path.parent)
    if path.exists() or path.is_symlink():
        if path.resolve(strict=True) != path or json.loads(path.read_text()) != value:
            raise ProjectFault('Another original SDK maintenance request owns admission.', 409)
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
        sync(path.parent)


def ungate(path, request_id):
    if path.exists() and json.loads(path.read_text()).get('requestId') == request_id:
        path.unlink(); sync(path.parent)


def qualification(root, r4os, identity, value):
    store = Jobs(root / 'Projects', r4os, identity)
    try:
        result = json.loads((root / (identity + '-build.json')).read_text())
        job = store.get(result['job']['id'])
        artifact = store.artifact(job['artifactId'])
        if job['state'] != 'completed' or job['pins'] != value['newPins'] or artifact['sdkProfile']['technical'] is not False:
            raise ProjectFault('The project has no matching successful SDK build qualification.', 409)
        expected = {item['path']: (item['sha256'], item['bytes'], item.get('executable', False)) for item in value['sourceBefore']['files']}
        changes = {item['path']: base64.b64decode(item['after']) for item in value['sdkFiles']}
        changes['.r4os-studio/project.json'] = base64.b64decode(value['newMetadata'])
        for path, data in changes.items():
            expected[path] = (hashlib.sha256(data).hexdigest(), len(data), expected.get(path, ('', 0, False))[2])
        actual = {item['path']: (item['sha256'], item['bytes'], item.get('executable', False)) for item in job['source']['files']}
        if actual != expected:
            raise ProjectFault('The successful SDK build differs from the proposed project sources. Keep migration pending.', 409)
        return {'jobId': job['id'], 'artifactId': artifact['id'], 'files': artifact['files'],
                'sourceSha256': job['source']['sha256'], 'buildProof': artifact['buildProof'], 'sdkProfile': artifact['sdkProfile']}
    finally:
        store.close()


async def migrate(args):
    original = Path(args.projects).resolve(strict=True); r4os = Path(args.root).resolve(strict=True)
    request_id = project_id(args.request_id); project_id(str(uuid.UUID(args.request_id)))
    qualification_root = Path(args.qualification_root).resolve(strict=True)
    sdk = sdk_provision.verify(r4os, args.sdk_id, sources=True)
    base = original / '.studio/sdk-migrations'; base.mkdir(mode=0o700, parents=True, exist_ok=True); folder(base)
    journal = base / (request_id + '.json')
    inputs = {'projects': str(original), 'r4os': str(r4os), 'sdk': args.sdk_id,
              'sdkManifestSha256': sdk['record']['manifestSha256'], 'qualificationRoot': str(qualification_root)}
    if journal.exists():
        state = json.loads(journal.read_text())
        if state['input'] != inputs:
            raise ProjectFault('This SDK migration identity belongs to different inputs.', 409)
    else:
        state = {'schema': 1, 'requestId': request_id, 'input': inputs, 'phase': 'prepared',
                 'before': projects(original), 'projects': {}, 'activationRequestId': str(uuid.uuid4()),
                 'defaultProfileRevision': profile_revision(json.loads((r4os / 'Profiles/versions.json').read_text()))}
        save(journal, state)
    project_gate = guard.path(original); component_gate = r4os / 'Profiles/sdk-host-maintenance.json'
    if state['phase'] == 'complete':
        for path in (project_gate, component_gate): ungate(path, request_id)
        print(json.dumps({'requestId': request_id, 'phase': 'complete', 'reconciled': True}), flush=True)
        return
    with ExitStack() as stack:
        lock = stack.enter_context((base / 'migration.lock').open('a'))
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gate(component_gate, request_id, 'sdk-profile-migration')
        status = component_status()
        if status.get('features', {}).get('sdkMigration') != 1 or (status.get('job') or {}).get('phase') == 'working':
            raise ProjectFault('Wait for the updated idle component host before continuing the original SDK migration.', 409)
        gate(project_gate, request_id, 'sdk-profile-migration')
        stack.enter_context(guard.own(original, request_id))
        current = projects(original)
        if [item['id'] for item in current] != [item['id'] for item in state['before']]:
            raise ProjectFault('The project inventory changed during SDK migration.', 409)
        for item in current:
            stack.enter_context(acquire(original, item['id'], exclusive=True, pins_recovery=True))
            workspace_lock = original / '.studio' / ('workspace-' + item['id'] + '.lock')
            lease = stack.enter_context(workspace_lock.open('a'))
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require_idle(original, item['id'])
        for unit in ('r4os-studio-agents.service', 'r4os-studio-development.service'):
            subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=True)
        hosts = {'agents': True, 'development': True}
        for item in current:
            ident = item['id']; planned = state['projects'].get(ident)
            if planned is None:
                before = next(record for record in state['before'] if record['id'] == ident)
                if item != before:
                    raise ProjectFault('A project changed before its SDK migration was prepared.', 409)
                choice = next(entry for entry in project_pins.choices(r4os, item) if entry['sdkId'] == args.sdk_id and entry['available'])
                data = {'requestId': str(uuid.uuid4()), 'revision': item['revision'], 'sdkId': args.sdk_id, 'selectionId': choice['selectionId']}
                state['projects'][ident] = planned = {'input': data}
                save(journal, state)
            value = project_pins.apply_locked(original, r4os, ident, planned['input'], hosts, prepare_only=True)
            if value.get('state') == 'complete':
                continue
            planned['qualification'] = qualification(qualification_root, r4os, ident, value)
            planned['newPins'] = value['newPins']; save(journal, state)
            print(json.dumps({'projectId': ident, 'phase': 'qualified'}), flush=True)
        from helper import prepare_helper
        from profiles import runner
        pins = next(iter(state['projects'].values()))['newPins'] if state['projects'] else None
        if pins is not None:
            helper = await prepare_helper(original, r4os, runner(), pins)
            state['helpers'] = {name: {key: value[key] for key in ('sha256', 'bytes', 'pins')}
                                for name, value in (('controller', helper), ('watchdog', helper['watchdog']))}
            save(journal, state)
        from service import Manager
        from sources import ADAPTERS
        manager = Manager(r4os, adapters=ADAPTERS)
        from r4upack import install as install_packer, choose
        packer = install_packer(manager, Path(args.packer_sources) if args.packer_sources else None, sdk_revision=args.sdk_id)
        state['packer'] = {key: packer[key] for key in ('id', 'sha256', 'profileSha256', 'sdkRevision')}; save(journal, state)
        for item in current:
            planned = state['projects'][item['id']]
            result = project_pins.apply_locked(original, r4os, item['id'], planned['input'], hosts)
            if result['state'] != 'complete' or result['project']['pins'] != planned['newPins']:
                raise ProjectFault('The original project SDK publication remains unconfirmed.', 409)
            planned['publishedRevision'] = result['project']['revision']; save(journal, state)
        from sdk_selection import start
        start(manager, 'default', args.sdk_id, state['activationRequestId'], state['defaultProfileRevision'], inputs['sdkManifestSha256'])
        while manager.busy:
            await asyncio.sleep(.25)
        if manager.state.get('sdkSelection', {}).get('requestId') != state['activationRequestId']:
            raise ProjectFault('The original SDK default activation remains unconfirmed.', 409)
        choose(r4os, packer['id'], [packer])
        state['after'] = projects(original)
        if any(item['pins'] != state['projects'][item['id']]['newPins'] for item in state['after']):
            raise ProjectFault('The final SDK project inventory does not match the original migration.', 409)
        state['phase'] = 'complete'; save(journal, state)
        for path in (project_gate, component_gate): ungate(path, request_id)
        print(json.dumps({'requestId': request_id, 'phase': 'complete', 'projects': len(state['after']), 'sdk': args.sdk_id}), flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('projects', 'root', 'request-id', 'sdk-id', 'qualification-root'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--packer-sources')
    parser.add_argument('--apply', action='store_true', required=True)
    args = parser.parse_args()
    asyncio.run(migrate(args))


if __name__ == '__main__':
    main()
