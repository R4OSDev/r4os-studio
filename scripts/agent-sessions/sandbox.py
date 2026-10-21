"""Project execution namespace, separate from the credential-bearing Codex namespace."""
import asyncio
from pathlib import Path
import sys
from profile import regular, digest, CODEX_SHA256


class Sandbox:
    def __init__(self, worker):
        self.worker = worker; self.context = None
        self.lock = asyncio.Lock(); self.initializing = asyncio.Lock()

    async def prepare(self):
        async with self.initializing:
            if self.context is not None: return
            from sdk import profile
            self.context = await asyncio.to_thread(profile, Path(self.worker.manifest['r4os']),
                              self.worker.store.projects, self.worker.config['projectPins'])
            binary = Path(self.worker.manifest['r4os']) / 'Toolchains/Codex' / self.worker.config['engine']['version'] / 'codex'
            if digest(regular(binary)) != CODEX_SHA256: raise ValueError('Unqualified patch engine.')
            self.binary = binary

    def command(self, command, workdir='/workspace'):
        args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        args += ['--symlink', '/usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                 '--dir', '/home', '--dir', '/home/studio', '--dir', '/etc',
                 '--bind', str(self.worker.store.workspace), '/workspace']
        for name, path in self.context['paths'].items():
            args += ['--ro-bind', str(path), '/' + name]
        if self.context.get('rust'):
            args += ['--ro-bind', str(self.context['rust']['prefix']), '/rust']
        args += ['--dir', '/runner', '--ro-bind', str(Path(__file__).parent / 'file_worker.py'), '/runner/file_worker.py',
                 '--ro-bind', str(self.binary), '/runner/codex', '--chdir', workdir, '--clearenv',
                 '--setenv', 'HOME', '/home/studio', '--setenv', 'PATH', '/zig:/rust/bin:/usr/bin:/bin',
                 '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'SDK_ROOT', '/sdk', '--setenv', 'CONTRACT_ROOT', '/contract',
                 '--setenv', 'CARGO_NET_OFFLINE', 'true', '--setenv', 'RUSTUP_TOOLCHAIN', 'studio-pinned',
                 '--setenv', 'ZIG_GLOBAL_CACHE_DIR', '/workspace/.studio-cache/zig',
                 '--setenv', 'CARGO_HOME', '/workspace/.studio-cache/cargo']
        return args + command

    async def file(self, name, arguments):
        import json
        await self.prepare()
        # All calls share this lock, including reads, so a read/hash pair observes
        # the preceding Studio write. External administrator edits remain external.
        async with self.lock:
            proc = await asyncio.create_subprocess_exec(*self.command(['/usr/bin/python3', '-I', '-B', '/runner/file_worker.py']),
                       stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=262144)
            try:
                output, _ = await asyncio.wait_for(proc.communicate(json.dumps({'tool': name, 'arguments': arguments}).encode()), 30)
                if proc.returncode or len(output) > 196608: raise ValueError()
                return json.loads(output)
            except BaseException:
                if proc.returncode is None: proc.kill(); await proc.wait()
                raise
