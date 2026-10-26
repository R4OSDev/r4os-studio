"""Durable package admission, qualified program binding and immutable package receipts."""
import json
from pathlib import Path
import stat
import uuid
from contracts import DevelopmentFault, digest, encode, hash_value, identity, LIMITS
from jobs import now, folder
from layout import save
from update_plans import read as plan_read, selected_packer, payload

PACKER_KEYS = ('id', 'version', 'revision', 'sdkRevision', 'host', 'sha256', 'profileSha256')


def tables(store):
    with store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS update_artifacts(id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL)')


def admit(store, request, owner=None):
    fields = {'requestId', 'projectRevision', 'planId', 'planSha256'}
    if not isinstance(request, dict) or set(request) != fields:
        raise DevelopmentFault('Unexpected package build fields.', 400)
    key = identity(request['requestId']); identity(request['planId'])
    if type(request['projectRevision']) is not int or not isinstance(request['planSha256'], str):
        raise DevelopmentFault('Invalid package plan/project revision.', 400)
    owner = owner or {'sessionId': None, 'agentRunId': None}
    fingerprint = hash_value({'kind': 'package', 'request': request, 'owner': owner})
    previous = store.db.execute('SELECT id,request_hash FROM jobs WHERE request_id=?', (key,)).fetchone()
    if previous:
        if previous['request_hash'] != fingerprint: raise DevelopmentFault('This request ID belongs to different package input.')
        return store.get(previous['id']), False
    if request['projectRevision'] != store.project['revision']: raise DevelopmentFault('Project settings changed. Reload before packaging.')
    plan = plan_read(store, request['planId'])
    if plan['sha256'] != request['planSha256'] or plan['pins'] != store.project['pins']:
        raise DevelopmentFault('The selected plan hash or project pins changed.')
    for part in plan['payloads']:
        if payload(store, part['artifactId']) != part: raise DevelopmentFault('A confirmed package input changed.')
    packer = selected_packer(store)
    if {key: packer[key] for key in PACKER_KEYS} != plan['packer']:
        raise DevelopmentFault('The selected Packer differs from this plan. Select the bound profile or create a new plan.')
    tables(store)
    store.db.execute('BEGIN IMMEDIATE')
    try:
        if store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchone(): raise DevelopmentFault('This project already has an active development job.')
        job = {'id': str(uuid.uuid4()), 'projectId': store.id, 'kind': 'package', 'state': 'queued', 'revision': 1,
            **owner, 'artifactId': None, 'deploymentId': None, 'packageArtifactId': None,
            'target': None, 'process': None, 'exitCode': None, 'error': None, 'phase': 'queued', 'check': None,
            'createdAt': now(), 'completedAt': None, 'source': None, 'projectRevision': store.project['revision'],
            'settingsRevision': store.settings()['revision'], 'pins': store.project['pins'], 'settings': store.settings(),
            'binding': None, 'updatePlan': plan}
        binding = {**packer, 'schema': 1, 'jobId': job['id'], 'projectId': store.id, 'planSha256': plan['sha256']}
        save(folder(store.root / 'PackageBindings') / (job['id'] + '.json'), binding)
        store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,1,1,?)', (job['id'], key, fingerprint, 'package', 'queued', encode(job)))
        store.db.commit(); return job, True
    except BaseException: store.db.rollback(); raise


def program(store, job):
    path = store.root / 'PackageBindings' / (identity(job['id']) + '.json')
    try:
        info = path.lstat()
        if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536: raise ValueError()
        value = json.loads(path.read_text())
        if (value['schema'] != 1 or value['projectId'] != store.id or value['jobId'] != job['id']
                or value['planSha256'] != job['updatePlan']['sha256']
                or {key: value[key] for key in PACKER_KEYS} != job['updatePlan']['packer']): raise ValueError()
        from r4upack import verify
        verified = verify(value['directory'], value['binary'])
        if any(verified[key] != value[key] for key in PACKER_KEYS if key != 'id'): raise ValueError()
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise DevelopmentFault('The accepted Packer binding is unavailable or changed. No package command started.') from None


def artifact(store, ident, recovering=False):
    tables(store)
    row = store.db.execute('SELECT payload FROM update_artifacts WHERE id=?', (identity(ident),)).fetchone()
    if not row: raise DevelopmentFault('Update package artifact not found.', 404)
    value = json.loads(row[0]); job = store.get(value['jobId'])
    if not recovering and (job['state'] != 'completed' or job.get('packageArtifactId') != ident):
        raise DevelopmentFault('The update package has no completed packaging receipt.')
    directory = store.root / 'UpdatePackages' / ident
    try:
        path = directory / 'package.R4U'; marker = directory / 'package.json'
        info = path.lstat()
        if (directory.resolve(strict=True) != directory or path.resolve(strict=True) != path or marker.resolve(strict=True) != marker
                or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 64 < info.st_size <= LIMITS['packageBytes']
                or value.get('schema') != 1 or value.get('format') != 'R4U2' or value.get('nativeExitCode') != 0
                or value['jobId'] != job['id'] or value.get('packer') != job['updatePlan']['packer']
                or value['projectId'] != store.id or value['plan'] != job['updatePlan']
                or value['bytes'] != info.st_size or digest(path) != value['sha256'] or json.loads(marker.read_text()) != value):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise DevelopmentFault('The immutable update package is missing or changed. Existing data was preserved.') from None
    return value


def publish(store, job_id, record):
    tables(store)
    store.db.execute('BEGIN IMMEDIATE')
    try:
        job = store.get(job_id)
        if job['state'] not in ('running', 'starting'): raise DevelopmentFault('Package publication stopped before confirmation.')
        store.db.execute('INSERT INTO update_artifacts VALUES(?,?,?)', (record['id'], job_id, encode(record)))
        job.update(state='completed', phase='completed', packageArtifactId=record['id'], exitCode=0, revision=job['revision'] + 1, completedAt=now())
        store.db.execute('UPDATE jobs SET state=?,busy=0,revision=?,payload=? WHERE id=?', ('completed', job['revision'], encode(job), job_id))
        store.db.commit(); return job
    except BaseException: store.db.rollback(); raise
