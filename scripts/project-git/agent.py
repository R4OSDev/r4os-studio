"""Verify an inherited active project-run lease without granting model socket or token access."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
from common import ProjectFault, folder, project_id, document


def process(pid):
    value = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()
    return int(value[1]), value[19]


class AgentLease:
    def __init__(self, config, identity, value, descriptor, peer_pid=None):
        self.projects, self.identity, self.value, self.fd = Path(config['projects']), project_id(identity), value, descriptor
        if (not isinstance(value, dict) or set(value) != {'sessionId', 'runId', 'workerPid', 'workerBirth', 'revision', 'callId'}
                or type(descriptor) is not int or type(value.get('workerPid')) is not int or value['workerPid'] <= 0
                or type(value.get('revision')) is not int or value['revision'] < 1 or not isinstance(value.get('callId'), str) or not 1 <= len(value['callId']) <= 256):
            raise ProjectFault('Invalid agent Git lease.', 403)
        project_id(value['sessionId']); project_id(value['runId'])
        if peer_pid is not None and process(peer_pid)[0] != value['workerPid']: raise ProjectFault('Git broker is not a child of this agent worker.', 403)

    def verify(self, projects=None, identity=None):
        if projects is not None and (Path(projects) != self.projects or identity != self.identity): raise ProjectFault('Git lease belongs to another project.', 403)
        path = folder(self.projects / '.studio') / ('workspace-' + self.identity + '.lock')
        info, held = path.lstat(), os.fstat(self.fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (info.st_dev, info.st_ino) != (held.st_dev, held.st_ino): raise ProjectFault('Agent workspace lease identity changed.', 403)
        try: fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError): raise ProjectFault('The inherited agent workspace lease is unavailable.', 403) from None
        path = folder(self.projects / self.identity / 'Sessions') / 'Sessions.sqlite'
        if path.resolve(strict=True) != path or not stat.S_ISREG(path.stat().st_mode): raise ProjectFault('Agent Git session storage is unavailable.', 503)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            row = db.execute('''SELECT r.state,r.busy,r.config,r.worker,s.revision FROM runs r JOIN sessions s ON s.id=r.session_id
                WHERE r.id=? AND s.id=? AND s.project_id=?''', (self.value['runId'], self.value['sessionId'], self.identity)).fetchone()
        if not row or row[0] not in ('starting', 'running') or row[1] != 1: raise ProjectFault('The agent run is no longer accepting Git effects.', 409)
        config, worker = json.loads(row[2]), json.loads(row[3] or '{}')
        if (config.get('owner') != {'type': 'project', 'id': self.identity} or config.get('engine', {}).get('profile') not in ('studio-tools-v6', 'studio-tools-v7', 'studio-tools-v8')
                or config.get('permissions', {}).get('studio.push_project') is not True or config.get('revision') != row[4] or row[4] != self.value['revision']
                or worker.get('pid') != self.value['workerPid'] or worker.get('birth') != self.value['workerBirth'] or process(self.value['workerPid'])[1] != self.value['workerBirth']):
            raise ProjectFault('Agent Git permission, profile or worker binding changed.', 403)
        from project_maintenance import project, pending_git, pending_update
        if config.get('projectPins') != project(self.projects, self.identity)['pins']: raise ProjectFault('The active agent project pins changed.', 409)
        if pending_git(self.projects, self.identity) or pending_update(self.projects, self.identity): raise ProjectFault('Resolve project recovery before an agent push.', 409)
        development = self.projects / self.identity / 'Development/Development.sqlite'
        if development.exists():
            if development.resolve(strict=True) != development: raise ProjectFault('Invalid development job storage.', 503)
            with closing(sqlite3.connect(development.as_uri() + '?mode=ro', uri=True)) as db:
                if db.execute('SELECT 1 FROM jobs WHERE busy=1 LIMIT 1').fetchone(): raise ProjectFault('Wait for development jobs before pushing.', 409)
