"""Original active-run authority and inherited workspace lease, never model scope."""
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from catalog import CatalogFault, fields, identity

PROFILE = 'studio-tools-v9'  # Activated with the complete declarations in 0.6.19.
PROFILES = ('studio-tools-v9','studio-tools-v10','studio-tools-v11','studio-tools-v12','studio-tools-v13','studio-tools-v14','studio-tools-v15')
TOOLS = ('get_remote_host', 'run_remote_command', 'remote_files', 'read_remote_job', 'stop_remote_job')


def encode(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def process(pid):
    value = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()
    return int(value[1]), value[19]


def ordinary(path):
    try:
        info = path.lstat()
        if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1: raise OSError()
    except OSError: raise CatalogFault('The original remote run binding is unavailable.', 403) from None
    return info


class Actor:
    def __init__(self, projects, project_id, context, descriptor, peer_pid):
        self.projects = Path(projects).absolute(); self.project_id = identity(project_id); self.context = context; self.fd = descriptor
        fields(context, ['sessionId', 'runId', 'workerPid', 'workerBirth', 'release', 'revision'])
        for key in ('sessionId', 'runId'): identity(context[key])
        if type(context['workerPid']) is not int or context['workerPid'] <= 0 or type(context['revision']) is not int or context['revision'] < 1:
            raise CatalogFault('Invalid remote worker binding.', 403)
        if process(peer_pid)[0] != context['workerPid']: raise CatalogFault('The remote sidecar is not this worker’s child.', 403)

    def verify(self, tool=None, call_id=None, arguments=None, cleanup=False):
        path = self.projects / '.studio' / ('workspace-' + self.project_id + '.lock')
        held, info = os.fstat(self.fd), ordinary(path)
        if (held.st_dev, held.st_ino) != (info.st_dev, info.st_ino): raise CatalogFault('The inherited workspace lease belongs to another project.', 403)
        try: fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError: raise CatalogFault('The original workspace lease is unavailable.', 403) from None
        path = self.projects / self.project_id / 'Sessions/Sessions.sqlite'; ordinary(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            row = db.execute('''SELECT r.state,r.busy,r.config,r.worker,s.revision,s.engine FROM runs r
                JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND s.id=? AND s.project_id=?''',
                (self.context['runId'], self.context['sessionId'], self.project_id)).fetchone()
            if not row or (not cleanup and (row[0] not in ('starting', 'running') or row[1] != 1)): raise CatalogFault('This run is no longer accepting remote work.', 403)
            config, worker = json.loads(row[2]), json.loads(row[3] or '{}')
            if (config.get('owner') != {'type': 'project', 'id': self.project_id} or config.get('engine', {}).get('profile') not in PROFILES
                    or json.loads(row[5]).get('profile') != config.get('engine',{}).get('profile')
                    or config.get('revision') != row[4] or row[4] != self.context['revision']
                    or worker.get('pid') != self.context['workerPid'] or worker.get('birth') != self.context['workerBirth']
                    or worker.get('release') != self.context['release'] or process(worker['pid'])[1] != worker['birth']):
                raise CatalogFault('Remote owner, profile, revision or original worker changed.', 403)
            if not cleanup:
                if tool not in TOOLS or config.get('permissions', {}).get('studio.' + tool) is not True:
                    raise CatalogFault('This run’s frozen remote permission is disabled.', 403)
                if not isinstance(call_id, str) or not 1 <= len(call_id) <= 256: raise CatalogFault('Invalid original remote tool call.', 403)
                intent = db.execute('SELECT tool,arguments_hash FROM tools WHERE run_id=? AND call_id=?', (self.context['runId'], call_id)).fetchone()
                fingerprint = hashlib.sha256(encode({'tool': 'studio_' + tool, 'arguments': arguments}).encode()).hexdigest()
                if not intent or intent != ('studio_' + tool, fingerprint): raise CatalogFault('The original remote tool intent changed.', 403)
            self.config = config
        return config

    def snapshot(self, tool, call_id):
        return {'projectId': self.project_id, **self.context, 'tool': tool, 'callId': call_id}


def still_running(projects, snapshot):
    try:
        path = Path(projects) / snapshot['projectId'] / 'Sessions/Sessions.sqlite'; ordinary(path)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
            row = db.execute('SELECT state,busy,worker FROM runs WHERE id=? AND session_id=?', (snapshot['runId'], snapshot['sessionId'])).fetchone()
        worker = json.loads(row[2] or '{}') if row else {}
        return bool(row and row[0] in ('starting', 'running') and row[1] == 1 and worker.get('pid') == snapshot['workerPid']
                    and worker.get('birth') == snapshot['workerBirth'] and worker.get('release') == snapshot['release']
                    and process(snapshot['workerPid'])[1] == snapshot['workerBirth'])
    except (OSError, ValueError, KeyError, sqlite3.Error): return False
