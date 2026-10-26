"""Git subprocesses see one source tree, one object store and a temporary auth socket."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import threading
import time
from common import ProjectFault, folder


@contextmanager
def credentials(base, token):
    path = base / 'credential.sock'
    if path.exists(): path.unlink()
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
                    _, uid, _ = struct.unpack('3i', client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                    request = client.recv(32)
                    if uid == os.getuid() and request in (b'username', b'password'):
                        client.sendall(b'x-access-token' if request == b'username' else token.encode())
                except OSError: pass
    thread = threading.Thread(target=serve, daemon=True); thread.start()
    try: yield path
    finally:
        stopped.set(); server.close(); thread.join(2); path.unlink(missing_ok=True)


class Git:
    def __init__(self, root, workspace, temporary, token=None):
        self.root, self.workspace, self.temporary, self.token = folder(root), folder(workspace), folder(temporary), token
        self.empty = self.temporary / 'empty'; self.empty.mkdir(mode=0o700, exist_ok=True)

    def command(self, args, auth=None):
        helper = Path(__file__).with_name('askpass.py')
        command = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-all', '--share-net',
                   '--ro-bind', '/usr', '/usr', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/home',
                   '--bind', str(self.root), '/repo', '--ro-bind', str(self.workspace), '/workspace', '--ro-bind', str(self.empty), '/empty', '--chdir', '/workspace']
        for item in ('/lib', '/lib64', '/etc/ssl', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group'):
            if Path(item).exists(): command += ['--ro-bind', item, item]
        if auth: command += ['--ro-bind', str(auth), '/credential.sock', '--ro-bind', str(helper), '/askpass.py']
        command += ['--', '/usr/bin/git', '-c', 'safe.directory=*', '-c', 'core.hooksPath=/empty', '-c', 'core.fsmonitor=false',
                    '-c', 'core.autocrlf=false', '-c', 'core.attributesFile=/dev/null', '-c', 'credential.helper=',
                    '-c', 'http.followRedirects=false', '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never',
                    '-c', 'submodule.recurse=false', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false']
        if args[0] != 'init': command += ['--git-dir=/repo', '--work-tree=/workspace']
        command += args
        return command

    def _run(self, args, auth, data, allow, timeout):
        env = {'PATH': '/usr/bin:/bin', 'HOME': '/home', 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
               'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TEMPLATE_DIR': '/empty', 'GIT_TERMINAL_PROMPT': '0',
               'GIT_ALLOW_PROTOCOL': 'https', 'GIT_PROTOCOL_FROM_USER': '0', 'GIT_ASKPASS': '/askpass.py'}
        out, err = self.temporary / 'stdout', self.temporary / 'stderr'
        with out.open('wb') as stdout, err.open('wb') as stderr:
            process = subprocess.Popen(self.command(args, auth), stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, env=env, start_new_session=True)
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
        if self.token:
            with credentials(self.temporary, self.token) as auth: return self._run(list(args), auth, data, allow, timeout)
        return self._run(list(args), None, data, allow, timeout)

    def text(self, *args, **kwargs): return self.run(*args, **kwargs)[0].decode('utf8').strip()

    def init(self, branch_name='main'):
        if not (self.root / 'HEAD').exists():
            self.run('init', '--bare', '--template=/empty', '--initial-branch=' + branch_name, '/repo')

    def head(self):
        out, code = self.run('rev-parse', '--verify', 'HEAD', allow=(0, 128))
        return out.decode().strip() if code == 0 else None
