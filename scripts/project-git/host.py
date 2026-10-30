#!/usr/bin/env python3
"""Unprivileged, fixed Unix Git coordinator. Requests never contain Git command lines or tokens."""
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import socketserver
import stat
import struct
import subprocess
import sys
import threading
import time
import fcntl
from common import ProjectFault, document, folder, now, project_id, save, digest, locks, binding

KINDS = ('initialize', 'bind', 'status', 'check', 'diff', 'create_repository', 'import', 'push', 'prepare_pull', 'pull')
READS = ('status', 'check', 'diff')


def birth(pid): return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]


class Coordinator:
    def __init__(self, config, config_path):
        self.config, self.config_path = config, config_path
        self.base = Path(config['projects']) / '.studio/github/Jobs'; self.base.mkdir(mode=0o700, parents=True, exist_ok=True); folder(self.base)
        self.lock = threading.RLock(); self.processes = {}; self.started = {}
        for directory in self.base.iterdir():
            project_id(directory.name); job = document(directory / 'job.json')
            if job['state'] in ('running', 'queued'):
                # A dead coordinator never repeats a previously accepted effect.
                job.update(state='unknown', error='Git coordinator restarted. Reconcile this original operation.', updatedAt=now()); save(directory / 'job.json', job)

    def release(self):
        root = Path('/opt/r4os-studio/current').resolve(strict=True)
        if not root.is_relative_to('/opt/r4os-studio/releases') or root.stat().st_uid != 0 or root.stat().st_mode & 0o022:
            raise ProjectFault('Invalid immutable Git worker release.', 503)
        script = root / 'scripts/project-git/worker.py'
        if not script.is_file() or script.stat().st_uid != 0 or script.stat().st_mode & 0o022: raise ProjectFault('Git worker release is unavailable.', 503)
        return str(root)

    def poll(self):
        for identity, process in list(self.processes.items()):
            if process.poll() is None and time.monotonic() - self.started.get(identity, time.monotonic()) > 300:
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None: continue
            path = self.base / identity / 'job.json'; job = document(path)
            if job['state'] in ('running', 'queued'):
                job.update(state='unknown', error='Git worker ended without a confirmed receipt.', updatedAt=now()); save(path, job)
            del self.processes[identity]
            self.started.pop(identity, None)

    def request(self, data, peer_pid=None, lease_fd=None):
        if not isinstance(data, dict): raise ProjectFault('Invalid Git request.', 400)
        operation = data.get('operation')
        with self.lock:
            self.poll()
            if operation == 'capabilities':
                manifest = document(Path(self.release()) / 'shared/project-git.json')
                if manifest.get('protocol') != 1 or any(v not in KINDS for v in manifest.get('actions', [])):
                    raise ProjectFault('Git release capabilities are incompatible.', 503)
                return {'available': True, 'protocol': 1, 'maxJobs': 2, 'kinds': manifest['actions'], 'limits': manifest['limits']}
            if operation == 'last_job':
                project = project_id(data.get('projectId'))
                matches = [document(path / 'job.json') for path in self.base.iterdir()]
                matches = [v for v in matches if v['projectId'] == project]
                actions = [v for v in matches if v['kind'] not in READS]
                unresolved = [v for v in actions if v['state'] == 'unknown']
                matches = unresolved or actions or matches
                return self.public(max(matches, key=lambda v: v['createdAt'])) if matches else None
            if operation in ('job', 'cancel', 'reconcile'):
                identity = project_id(data.get('requestId')); project_id(data.get('projectId'))
                path = self.base / identity / 'job.json'
                if not path.exists(): raise ProjectFault('Git job not found.', 404)
                job = document(path)
                if job['projectId'] != data['projectId']: raise ProjectFault('Git job belongs to another project.', 403)
                if operation == 'reconcile' and job['state'] == 'unknown':
                    with open(path.with_name('execution.lock'), 'a') as lease:
                        try: fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError: raise ProjectFault('The original Git worker is still active. Wait for its receipt.', 409) from None
                        if job['kind'] == 'import':
                            from importing import reconcile
                            from project_use import acquire
                            with acquire(self.config['projects'], job['projectId'], exclusive=True): result = reconcile(self.config, job)
                        else:
                            from operations import reconcile
                            with locks(self.config['projects'], job['projectId'], mutate=job['kind'] not in READS, recovery=job['kind'] == 'pull'):
                                result = reconcile(self.config, job)
                        if result is not None:
                            job.update(state='completed', phase='reconciled', result=result, error=None, updatedAt=now()); save(path, job)
                    return self.public(job)
                if operation == 'cancel' and identity in self.processes:
                    os.killpg(self.processes[identity].pid, signal.SIGTERM)
                    job.update(state='unknown', error='Git operation stopped. Reconcile any pending effect.', updatedAt=now()); save(path, job)
                return self.public(job)
            agent = operation == 'agent_submit'
            if operation not in ('submit', 'agent_submit') or set(data) != ({'operation', 'projectId', 'requestId', 'kind', 'input'} | ({'agent'} if agent else set())):
                raise ProjectFault('Unsupported Git request.', 400)
            identity, project = project_id(data['requestId']), project_id(data['projectId'])
            if agent:
                from agent import AgentLease
                if data['kind'] != 'push' or not isinstance(data.get('input'), dict) or set(data['input']) - {'commitMessage', 'files'}: raise ProjectFault('The agent Git broker supports project push only.', 400)
                AgentLease(self.config, project, data['agent'], lease_fd, peer_pid).verify()
            elif lease_fd is not None: raise ProjectFault('Unexpected inherited Git lease.', 400)
            if data['kind'] not in KINDS or not isinstance(data['input'], dict): raise ProjectFault('Invalid Git job kind.', 400)
            fingerprint = digest(data)
            directory = self.base / identity; path = directory / 'job.json'
            if directory.exists():
                old = document(path)
                if old['hash'] != fingerprint: raise ProjectFault('This Git request ID belongs to different input.', 409)
                return self.public(old)
            check_binding = None
            if data['kind'] == 'check':
                if set(data['input']) - {'bindingRevision'}: raise ProjectFault('Invalid remote check fields.', 400)
                bound = binding(self.config['projects'], project)
                expected = data['input'].get('bindingRevision')
                if 'bindingRevision' in data['input'] and (type(expected) is not int or not bound or expected != bound['revision']):
                    raise ProjectFault('The repository binding changed. Refresh before checking.', 409)
                check_binding = digest(bound)
                if expected is not None:
                    for process_id in self.processes:
                        old = document(self.base / process_id / 'job.json')
                        if old['projectId'] == project and old['kind'] == 'check' and old['state'] in ('queued', 'running') and old.get('checkBinding') == check_binding:
                            return self.public(old)
            if len(self.processes) >= 2: raise ProjectFault('Two Git jobs are already active. Retry shortly.', 409)
            for process_id in self.processes:
                if document(self.base / process_id / 'job.json')['projectId'] == project: raise ProjectFault('This project already has an active Git job.', 409)
            for previous in self.base.iterdir():
                old = document(previous / 'job.json')
                if data['kind'] not in READS and old['projectId'] == project and old['state'] == 'unknown' and old['kind'] not in READS:
                    raise ProjectFault('Resolve the original uncertain Git job before another operation.', 409)
            release = self.release()
            if data['kind'] not in document(Path(release) / 'shared/project-git.json')['actions']:
                raise ProjectFault('This Git operation requires a newer installed release.', 409)
            directory.mkdir(mode=0o700)
            job = {'schema': 1, 'id': identity, 'projectId': project, 'kind': data['kind'], 'input': data['input'], 'hash': fingerprint,
                   'releaseRoot': release, 'state': 'queued', 'phase': 'accepted', 'createdAt': now(), 'updatedAt': now()}
            if agent: job['agent'] = data['agent']
            if check_binding is not None: job['checkBinding'] = check_binding
            save(path, job)
            try:
                process = subprocess.Popen(['/usr/bin/python3', '-B', release + '/scripts/project-git/worker.py', str(self.config_path), identity] + ([str(lease_fd)] if agent else []),
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, start_new_session=True, pass_fds=(lease_fd,) if agent else ())
                self.processes[identity] = process
                self.started[identity] = time.monotonic()
            except OSError:
                job.update(state='failed', error='Git worker could not be started.', code=503); save(path, job)
            return self.public(job)

    @staticmethod
    def public(job):
        return {k: job[k] for k in ('id', 'projectId', 'kind', 'state', 'phase', 'createdAt', 'updatedAt', 'result', 'error', 'code') if k in job}


def main():
    os.umask(0o077)
    config_path = Path('/etc/r4os-studio-git/config.json'); config = document(config_path)
    if os.getuid() != config['uid']: raise SystemExit('Git coordinator requires its fixed unprivileged account.')
    coordinator = Coordinator(config, config_path)
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(5); descriptors = []
            try:
                peer_pid, uid, _ = struct.unpack('3i', self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != config['uid']: raise ProjectFault('Git coordinator peer is not allowed.', 403)
                raw = b''
                while b'\n' not in raw:
                    part, ancillary, flags, _ = self.request.recvmsg(65536, socket.CMSG_SPACE(16))
                    for level, kind, value in ancillary:
                        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS: descriptors.extend(struct.unpack(str(len(value) // 4) + 'i', value))
                    if flags & socket.MSG_CTRUNC or len(descriptors) > 1: raise ProjectFault('Invalid Git lease transfer.', 400)
                    if not part: raise ProjectFault('Incomplete Git request.', 400)
                    raw += part
                    if len(raw) > 262144: raise ProjectFault('Git request exceeds its limit.', 400)
                response = {'result': coordinator.request(json.loads(raw), peer_pid, descriptors[0] if descriptors else None)}
            except ProjectFault as error: response = {'error': str(error), 'code': error.code}
            except Exception: response = {'error': 'Git service could not confirm this request.', 'code': 503}
            finally:
                for descriptor in descriptors: os.close(descriptor)
            self.request.sendall((json.dumps(response, ensure_ascii=False) + '\n').encode())
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True; request_queue_size = 8
    path = Path('/run/r4os-studio-git/control.sock'); path.unlink(missing_ok=True)
    with Server(str(path), Handler) as server:
        os.chmod(path, 0o600); server.timeout = 1
        while True:
            server.handle_request()
            with coordinator.lock:
                coordinator.poll()
                # Adopt new immutable host code only at idle; old accepted workers remain pinned.
                release = coordinator.release()
                if not coordinator.processes and release != str(Path(__file__).resolve().parents[2]):
                    os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', release + '/scripts/project-git/host.py'])


if __name__ == '__main__': main()
