"""Git subprocesses see one source tree, one object store and a temporary auth socket."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
import signal
import socket
import struct
import subprocess
import threading
import time
import tempfile
from common import ProjectFault, folder


@contextmanager
def credentials(base, token):
    # Unix socket names are limited to108 bytes. Project UUID/staging paths can
    # be longer; a private short-lived directory also works in service PrivateTmp.
    temporary = tempfile.TemporaryDirectory(prefix='studio-git-auth-', dir='/tmp')
    path = Path(temporary.name) / 'credential.sock'
    server = socket.socket(socket.AF_UNIX); server.bind(str(path)); os.chmod(path, 0o600); server.listen(2); server.settimeout(.2)
    stopped = threading.Event()
    def serve():
        while not stopped.is_set():
            try: client, _ = server.accept()
            except TimeoutError: continue
            except OSError: break
            with client:
                client.settimeout(2)
                try:
                    request = client.recv(32)
                    if request in (b'username', b'password'):
                        client.sendall(b'x-access-token' if request == b'username' else token.encode())
                except OSError: pass
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    try: yield path
    finally:
        stopped.set(); server.close(); thread.join(2); path.unlink(missing_ok=True); temporary.cleanup()


class Git:
    def __init__(self, root, workspace, temporary, token=None, read_only=False):
        self.root, self.workspace, self.temporary, self.token = folder(root), folder(workspace), folder(temporary), token
        self.read_only = read_only
        self.empty = self.temporary / 'empty'; self.empty.mkdir(mode=0o700, exist_ok=True)

    def command(self, args, auth=None):
        helper = Path(__file__).with_name('askpass.py')
        command = []
        command += ['/usr/bin/git', '-c', 'safe.directory=*', '-c', 'core.hooksPath=' + str(self.empty), '-c', 'core.fsmonitor=false',
                    '-c', 'core.autocrlf=false', '-c', 'core.attributesFile=/dev/null', '-c', 'credential.helper=',
                    '-c', 'http.followRedirects=false', '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never',
                    '-c', 'submodule.recurse=false', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false']
        if args[0] != 'init': command += ['--git-dir=' + str(self.root), '--work-tree=' + str(self.workspace)]
        command += list(map(str, args))
        return command

    def _run(self, args, auth, data, allow, timeout):
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.temporary), 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TEMPLATE_DIR': str(self.empty), 'GIT_TERMINAL_PROMPT': '0', 'GIT_LITERAL_PATHSPECS': '1',
               'GIT_ALLOW_PROTOCOL': 'https', 'GIT_PROTOCOL_FROM_USER': '0', 'GIT_ASKPASS': str(Path(__file__).with_name('askpass.py'))}
        if self.read_only: env['GIT_OPTIONAL_LOCKS'] = '0'
        out, err = self.temporary / 'stdout', self.temporary / 'stderr'
        with out.open('wb') as stdout, err.open('wb') as stderr:
            process = subprocess.Popen(self.command(args, auth), stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, env={**env, **({'STUDIO_GIT_AUTH_SOCKET': str(auth)} if auth else {})}, cwd=self.workspace, start_new_session=True)
            stopped, exceeded = threading.Event(), threading.Event()
            def monitor():
                while not stopped.wait(.25):
                    try:
                        size, count = 0, 0
                        for entry in self.root.rglob('*'):
                            count += 1
                            if entry.is_file(): size += entry.stat().st_size
                            if count > 40000 or size > 512 * 1024 * 1024: break
                        if count > 40000 or size > 512 * 1024 * 1024 or out.stat().st_size > 40 * 1024 * 1024 or err.stat().st_size > 1024 * 1024:
                            exceeded.set(); os.killpg(process.pid, signal.SIGKILL); return
                    except OSError: pass
            watcher = threading.Thread(target=monitor, daemon=True); watcher.start()
            try: process.communicate(data, timeout=timeout)
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL); process.wait(); raise ProjectFault('Git command was interrupted; reconcile the original operation.', 503) from None
            finally: stopped.set(); watcher.join(2)
        if exceeded.is_set() or out.stat().st_size > 40 * 1024 * 1024 or err.stat().st_size > 1024 * 1024:
            raise ProjectFault('Git command output exceeded its limit.', 409)
        result = out.read_bytes()
        if process.returncode not in allow:
            # Upstream text can contain credentials; return fixed diagnostics only.
            raise ProjectFault('Git operation failed. Check repository access, branch rules and the latest remote state. Local data was preserved.', 409)
        return result, process.returncode

    def run(self, *args, data=None, allow=(0,), timeout=60):
        if self.read_only and (not args or args[0] not in ('rev-parse','symbolic-ref','rev-list','ls-files','status','diff') or data is not None):
            raise ProjectFault('This Git inspection permits fixed read-only commands only.',403)
        if self.token:
            with credentials(self.temporary, self.token) as auth: return self._run(list(args), auth, data, allow, timeout)
        return self._run(list(args), None, data, allow, timeout)

    def text(self, *args, **kwargs): return self.run(*args, **kwargs)[0].decode('utf8').strip()

    def init(self, branch_name='main'):
        if not (self.root / 'HEAD').exists():
            self.run('init', '--bare', '--template=' + str(self.empty), '--initial-branch=' + branch_name, str(self.root))
        # Retain the local exclusion even when a remote .gitignore changes.
        info = self.root / 'info'; info.mkdir(mode=0o700, exist_ok=True); folder(info)
        exclude = info / 'exclude'
        if exclude.is_symlink() or (exclude.exists() and not exclude.is_file()):
            raise ProjectFault('Invalid local Git exclusion file.', 503)
        existing = exclude.read_bytes() if exclude.exists() else b''
        if b'/ExFiles/' not in existing.splitlines():
            with exclude.open('ab') as stream:
                stream.write((b'\n' if existing and not existing.endswith(b'\n') else b'') + b'/ExFiles/\n')

    def head(self):
        out, code = self.run('rev-parse', '--verify', 'HEAD', allow=(0, 128))
        return out.decode().strip() if code == 0 else None
