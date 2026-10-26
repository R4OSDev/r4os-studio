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
from common import ProjectFault, document, folder, now, project_id, save, digest

KINDS = ('initialize', 'bind', 'status', 'check', 'create_repository', 'import', 'push', 'pull')


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

    def request(self, data):
        if not isinstance(data, dict): raise ProjectFault('Invalid Git request.', 400)
        operation = data.get('operation')
        with self.lock:
            self.poll()
            if operation == 'capabilities':
                manifest = document(Path(self.release()) / 'shared/project-git.json')
                if manifest.get('protocol') != 1 or any(v not in KINDS for v in manifest.get('actions', [])):
                    raise ProjectFault('Git release capabilities are incompatible.', 503)
                return {'available': True, 'protocol': 1, 'maxJobs': 2, 'kinds': manifest['actions'], 'limits': manifest['limits']}
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
                        from operations import reconcile
                        result = reconcile(self.config, job)
                        if result is not None:
                            job.update(state='completed', phase='reconciled', result=result, error=None, updatedAt=now()); save(path, job)
                    return self.public(job)
                if operation == 'cancel' and identity in self.processes:
                    os.killpg(self.processes[identity].pid, signal.SIGTERM)
                    job.update(state='unknown', error='Git operation stopped. Reconcile any pending effect.', updatedAt=now()); save(path, job)
                return self.public(job)
            if operation != 'submit' or set(data) != {'operation', 'projectId', 'requestId', 'kind', 'input'}:
                raise ProjectFault('Unsupported Git request.', 400)
            identity, project = project_id(data['requestId']), project_id(data['projectId'])
            if data['kind'] not in KINDS or not isinstance(data['input'], dict): raise ProjectFault('Invalid Git job kind.', 400)
            fingerprint = digest(data)
            directory = self.base / identity; path = directory / 'job.json'
            if directory.exists():
                old = document(path)
                if old['hash'] != fingerprint: raise ProjectFault('This Git request ID belongs to different input.', 409)
                return self.public(old)
            if len(self.processes) >= 2: raise ProjectFault('Two Git jobs are already active. Retry shortly.', 409)
            for process_id in self.processes:
                if document(self.base / process_id / 'job.json')['projectId'] == project: raise ProjectFault('This project already has an active Git job.', 409)
            for previous in self.base.iterdir():
                old = document(previous / 'job.json')
                if data['kind'] not in ('status', 'check') and old['projectId'] == project and old['state'] == 'unknown' and old['kind'] not in ('status', 'check'):
                    raise ProjectFault('Resolve the original uncertain Git job before another operation.', 409)
            release = self.release()
            directory.mkdir(mode=0o700)
            job = {'schema': 1, 'id': identity, 'projectId': project, 'kind': data['kind'], 'input': data['input'], 'hash': fingerprint,
                   'releaseRoot': release, 'state': 'queued', 'phase': 'accepted', 'createdAt': now(), 'updatedAt': now()}
            save(path, job)
            try:
                process = subprocess.Popen(['/usr/bin/python3', '-B', release + '/scripts/project-git/worker.py', str(self.config_path), identity],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}, start_new_session=True)
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
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            try:
                _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid != config['uid']: raise ProjectFault('Git coordinator peer is not allowed.', 403)
                raw = self.rfile.readline(262145)
                if len(raw) > 262144: raise ProjectFault('Git request exceeds its limit.', 400)
                response = {'result': coordinator.request(json.loads(raw))}
            except ProjectFault as error: response = {'error': str(error), 'code': error.code}
            except Exception: response = {'error': 'Git service could not confirm this request.', 'code': 503}
            self.wfile.write((json.dumps(response, ensure_ascii=False) + '\n').encode())
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
