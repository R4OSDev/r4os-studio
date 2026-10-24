"""Durable, project-scoped development jobs; no automatic replay of effects."""
import datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import uuid

from contracts import ACTIVE, TERMINAL, DevelopmentFault, encode, hash_value, identity, LIMITS, relative, digest
sys.path.append(str(Path(__file__).resolve().parents[1] / 'projects'))
from store import connect, public
from layout import workspace, save


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def folder(path):
    path = Path(path).absolute()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.resolve(strict=True) != path or not stat.S_ISDIR(path.lstat().st_mode):
        raise DevelopmentFault('Invalid development storage.', 503)
    return path


class Jobs:
    def __init__(self, projects, r4os, project_id):
        from project_use import acquire
        self.project_use = acquire(projects, project_id)
        try: self.open(projects, r4os, project_id)
        except BaseException:
            self.project_use.close(); raise

    def open(self, projects, r4os, project_id):
        self.projects, self.r4os, self.id = Path(projects), Path(r4os), identity(project_id)
        db = connect(self.projects)
        try:
            self.project = public(db.execute("SELECT * FROM projects WHERE id=? AND state='ready'", (self.id,)).fetchone())
        finally: db.close()
        self.workspace = workspace(self.projects, self.id, True)
        self.root = folder(self.projects / self.id / 'Development')
        path = self.root / 'Development.sqlite'
        for p in (path, path.with_name(path.name + '-journal')):
            if p.is_symlink() or (p.exists() and not stat.S_ISREG(p.lstat().st_mode)):
                raise DevelopmentFault('Invalid development database.', 503)
        self.db = sqlite3.connect(path, timeout=5); self.db.row_factory = sqlite3.Row
        path.chmod(0o600); self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('BEGIN IMMEDIATE')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1): raise DevelopmentFault('Development data maintenance is required.', 503)
        with self.db:
            if version == 0:
                if self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise DevelopmentFault('Unrecognized development data.', 503)
                self.db.executescript('''
                  CREATE TABLE jobs(id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    request_hash TEXT NOT NULL, kind TEXT NOT NULL, state TEXT NOT NULL,
                    busy INTEGER NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL);
                  CREATE UNIQUE INDEX active_project_job ON jobs(busy) WHERE busy=1;
                  CREATE TABLE settings(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
                  CREATE TABLE artifacts(id TEXT PRIMARY KEY, build_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL);
                  PRAGMA user_version=1;
                ''')
                self.db.execute('INSERT INTO settings VALUES(1,?)', (encode({'revision': 1,
                    'arguments': '', 'workingDirectory': '.', 'timeoutSeconds': 60,
                    'expectedExitCode': None, 'outputContains': [], 'visualCriteria': ''}),))
        # Additive schema-1 extension: earlier build workers ignore this table.
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS deployments(id TEXT PRIMARY KEY, job_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')

    def close(self):
        self.db.close(); self.project_use.close()
    def settings(self):
        from settings import DEFAULTS
        return {**DEFAULTS, **json.loads(self.db.execute('SELECT payload FROM settings WHERE id=1').fetchone()[0])}

    def get(self, job_id):
        row = self.db.execute('SELECT payload FROM jobs WHERE id=?', (identity(job_id),)).fetchone()
        if not row: raise DevelopmentFault('Development job not found.', 404)
        return json.loads(row[0])

    def list(self):
        values = [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 100')]
        for value in values:
            if value.get('source'): value['source'] = {k: v for k, v in value['source'].items() if k not in ('files', 'directories')}
        return values

    def admit(self, kind, request, owner=None, binding=None):
        if kind not in ('build', 'deploy', 'execution', 'vm_start'): raise DevelopmentFault('This development operation is not available.', 400)
        expected = {'requestId', 'projectRevision', 'settingsRevision'} | ({'artifactId'} if kind == 'deploy' else ({'deploymentId'} if kind == 'execution' else set()))
        if kind == 'execution' and 'overrides' in request: expected.add('overrides')
        if set(request) != expected:
            raise DevelopmentFault('Unexpected development fields.', 400)
        identity(request['requestId'])
        if any(type(request[k]) != int or request[k] < 1 for k in ('projectRevision', 'settingsRevision')):
            raise DevelopmentFault('Invalid development revision.', 400)
        owner = owner or {'sessionId': None, 'agentRunId': None}
        fingerprint = hash_value({'kind': kind, 'request': request, 'owner': owner})
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous = self.db.execute('SELECT id,request_hash FROM jobs WHERE request_id=?', (request['requestId'],)).fetchone()
            if previous:
                if previous['request_hash'] != fingerprint: raise DevelopmentFault('This request ID belongs to different development input.')
                self.db.commit(); return self.get(previous['id']), False
            if request['projectRevision'] != self.project['revision'] or request['settingsRevision'] != self.settings()['revision']:
                raise DevelopmentFault('Project or Run & Test settings changed. Reload before starting.')
            if self.db.execute('SELECT id FROM jobs WHERE busy=1').fetchone():
                raise DevelopmentFault('This project already has an active development job.')
            deployment = self.deployment_metadata(request['deploymentId']) if kind == 'execution' else None
            artifact = self.artifact(request['artifactId'] if kind == 'deploy' else deployment['artifactId']) if kind in ('deploy', 'execution') else None
            if deployment and (deployment['target']['vmId'] != self.project['vmId'] or deployment.get('pins') != self.project['pins']):
                raise DevelopmentFault('This deployment belongs to a different project target or component identity.')
            if kind == 'execution' and self.settings()['workingDirectory'] != '.':
                raise DevelopmentFault('Only the deployment directory is a qualified R4OS working directory.')
            if artifact and artifact.get('pins') != self.project['pins']:
                raise DevelopmentFault('The artifact pins differ from the current project identity.')
            settings = self.settings()
            if 'overrides' in request:
                from settings import validate
                overrides = request['overrides']
                if not isinstance(overrides, dict) or set(overrides) - {'arguments', 'timeoutSeconds', 'expectedExitCode', 'outputContains', 'outputFiles', 'serviceResponseContains', 'visualCriteria'}:
                    raise DevelopmentFault('Unexpected execution overrides.', 400)
                settings = validate({**settings, **overrides})
                if self.project['template'] == 'service' and len(settings['arguments'].encode()) > 95:
                    raise DevelopmentFault('Service arguments are limited to 95 bytes.', 400)
                if settings.get('serviceResponseContains') and self.project['template'] != 'service':
                    raise DevelopmentFault('This project is not a service.', 400)
            job = {'id': str(uuid.uuid4()), 'projectId': self.id, 'kind': kind, 'state': 'queued',
                'revision': 1, **owner, 'artifactId': artifact['id'] if artifact else None, 'deploymentId': deployment['id'] if deployment else None,
                'target': None, 'process': None, 'exitCode': None, 'error': None,
                'phase': 'queued', 'check': None, 'createdAt': now(), 'completedAt': None,
                'source': None, 'projectRevision': self.project['revision'],
                'settingsRevision': self.settings()['revision'], 'pins': self.project['pins'], 'binding': binding,
                'settings': settings}
            self.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,1,1,?)',
                (job['id'], request['requestId'], fingerprint, kind, 'queued', encode(job)))
            self.db.commit(); return job, True
        except BaseException: self.db.rollback(); raise

    def update(self, job_id, state=None, **fields):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            job = self.get(job_id)
            if job['state'] in TERMINAL:
                self.db.commit(); return job
            state = state or job['state']
            if state not in (*ACTIVE, *TERMINAL): raise ValueError('Invalid job state.')
            if job['state'] == 'stopping' and state in ('queued', 'starting', 'running'): state = 'stopping'
            job.update(fields); job['state'] = state; job['revision'] += 1
            if state in TERMINAL: job['completedAt'] = now()
            self.db.execute('UPDATE jobs SET state=?,busy=?,revision=?,payload=? WHERE id=?',
                (state, int(state in ACTIVE), job['revision'], encode(job), job_id))
            self.db.commit(); return job
        except BaseException: self.db.rollback(); raise

    def annotate(self, job_id, **fields):
        if set(fields) - {'check', 'visualAssessment'}: raise ValueError('Invalid job annotation.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            job = self.get(job_id); job.update(fields); job['revision'] += 1
            self.db.execute('UPDATE jobs SET revision=?,payload=? WHERE id=?', (job['revision'], encode(job), job_id))
            self.db.commit(); return job
        except BaseException: self.db.rollback(); raise

    def page(self, job_id, offset=0):
        job = self.get(job_id)
        if job.get('source'): job['source'] = {k: v for k, v in job['source'].items() if k not in ('files', 'directories')}
        if type(offset) != int or offset < 0 or offset > LIMITS['outputBytes']:
            raise DevelopmentFault('Invalid development output offset.', 400)
        path = self.root / 'Evidence' / job_id / 'output.log'
        data = b''
        if path.exists():
            if path.is_symlink() or path.resolve() != path: raise DevelopmentFault('Invalid development evidence.', 503)
            with path.open('rb') as stream: stream.seek(offset); data = stream.read(LIMITS['pageBytes'])
            if len(data) == LIMITS['pageBytes']:
                try: data.decode('utf-8')
                except UnicodeDecodeError as error:
                    if error.reason == 'unexpected end of data' and error.end == len(data): data = data[:error.start]
        from evidence import list_for
        return {'job': job, 'output': data.decode('utf-8', errors='replace'), 'nextOffset': offset + len(data),
                'truncated': path.exists() and path.stat().st_size >= LIMITS['outputBytes'],
                'outputKind': 'build' if job['kind'] == 'build' else 'diagnostic' if job['kind'] == 'vm_start' else 'console', 'evidence': list_for(self, job_id)}

    def artifact_metadata(self, artifact_id, recovering=False):
        """Private ownership lookup; callers must verify bytes before using files."""
        row = self.db.execute('SELECT payload FROM artifacts WHERE id=?', (identity(artifact_id),)).fetchone()
        if not row: raise DevelopmentFault('Development artifact not found.', 404)
        record = json.loads(row[0])
        build = self.get(record['buildId'])
        if build['kind'] != 'build' or (not recovering and (build['state'] != 'completed' or build['artifactId'] != artifact_id)):
            raise DevelopmentFault('This artifact has no completed build receipt.')
        return record

    def artifact(self, artifact_id, recovering=False):
        record = self.artifact_metadata(artifact_id, recovering)
        root = self.root / 'Artifacts' / artifact_id
        try:
            if root.resolve(strict=True) != root or json.loads((root / 'artifact.json').read_text()) != record:
                raise ValueError()
            proof = root / 'build-proof.json'
            if proof.resolve(strict=True) != proof or proof.stat().st_size != record['buildProof']['bytes'] or digest(proof) != record['buildProof']['sha256']:
                raise ValueError()
            for item in record['files']:
                path = root / relative(item['path'])
                if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_nlink != 1:
                    raise ValueError()
                if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']: raise ValueError()
            if hash_value(record['files']) != record['packageSha256']: raise ValueError()
        except (OSError, ValueError, KeyError):
            raise DevelopmentFault('The artifact is missing or its checksum changed. Build a new artifact.') from None
        return record

    def publish(self, job_id, record):
        # Directory publication precedes the receipt. Recovery can inspect it;
        # a missing receipt never turns a failed job into a previous success.
        with self.db:
            self.db.execute('INSERT INTO artifacts VALUES(?,?,?)', (record['id'], job_id, encode(record)))
        return self.update(job_id, 'completed', phase='completed', artifactId=record['id'], exitCode=0)

    def publish_deployment(self, job_id, record):
        with self.db: self.db.execute('INSERT INTO deployments VALUES(?,?,?)', (record['id'], job_id, encode(record)))
        return self.update(job_id, 'completed', phase='completed', deploymentId=record['id'], target=record['target'], exitCode=0)

    def deployment_metadata(self, deployment_id, recovering=False):
        """Private ownership lookup without reading an artifact's bytes."""
        row = self.db.execute('SELECT payload FROM deployments WHERE id=?', (identity(deployment_id),)).fetchone()
        if not row: raise DevelopmentFault('Deployment not found.', 404)
        value = json.loads(row[0]); job = self.get(value['jobId'])
        if not recovering and (job['state'] != 'completed' or job['deploymentId'] != deployment_id):
            raise DevelopmentFault('The deployment has no completed verification receipt.')
        return value

    def deployment(self, deployment_id, recovering=False):
        value = self.deployment_metadata(deployment_id, recovering)
        self.artifact(value['artifactId'])
        return value

    def recovered(self, job_id, state, receipt, **fields):
        with self.db: self.db.execute('CREATE TABLE IF NOT EXISTS recoveries(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,previous TEXT NOT NULL,receipt TEXT NOT NULL)')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous = self.get(job_id)
            if previous['state'] != 'unknown': raise DevelopmentFault('Only an unconfirmed job can be reconciled.')
            self.db.execute('INSERT INTO recoveries VALUES(?,?,?,?)', (identity(receipt['id']), job_id, encode(previous), encode(receipt)))
            job = {**previous, **fields, 'state': state, 'phase': 'reconciled', 'recovery': receipt,
                'revision': previous['revision'] + 1, 'completedAt': previous['completedAt'] or now()}
            self.db.execute('UPDATE jobs SET state=?,busy=0,revision=?,payload=? WHERE id=?', (state, job['revision'], encode(job), job_id))
            self.db.commit(); return job
        except BaseException: self.db.rollback(); raise

    def evidence(self, job_id): return folder(self.root / 'Evidence' / identity(job_id))

    def agent_busy(self):
        path = self.projects / self.id / 'Sessions/Sessions.sqlite'
        if not path.exists(): return False
        if path.is_symlink(): raise DevelopmentFault('Invalid session storage.', 503)
        db = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True, timeout=5)
        try: return bool(db.execute('SELECT id FROM runs WHERE busy=1').fetchone())
        finally: db.close()
