"""Project execution namespace, separate from the credential-bearing Codex namespace."""
import asyncio
import os
from pathlib import Path
import shutil
import sys
from profile import regular, digest, directory, CODEX_SHA256


class Sandbox:
    def __init__(self, worker):
        self.worker = worker; self.context = None
        self.lock = asyncio.Lock(); self.initializing = asyncio.Lock()

    async def prepare(self):
        async with self.initializing:
            if self.context is not None: return
            if self.worker.store.owner_type == 'skill':
                context = {'paths': {}}
            else:
                from sdk import profile
                context = await asyncio.to_thread(profile, Path(self.worker.manifest['r4os']),
                                  self.worker.store.projects, self.worker.config['projectPins'])
            binary = Path(self.worker.manifest['r4os']) / 'Toolchains/Codex' / self.worker.config['engine']['version'] / 'codex'
            if digest(regular(binary)) != CODEX_SHA256: raise ValueError('Unqualified patch engine.')
            self.binary = binary
            # A private run cache never follows source-controlled symlinks and
            # never exposes the session DB or the credential-bearing namespace.
            self.cache = directory(self.worker.store.directory / self.worker.session_id / 'Tools' / self.worker.run_id)
            for name in ('home', 'zig', 'cargo'): directory(self.cache / name)
            if self.worker.store.owner_type == 'project':
                package_link = self.cache / 'zig/p'
                if not package_link.exists() and not package_link.is_symlink(): package_link.symlink_to('/packages')
                if os.readlink(package_link) != '/packages': raise ValueError('Invalid tool package cache.')
            exports = context.get('sdkTools') or context.get('rust')
            if exports:
                # Official build scripts chmod their catalog; shared tools stay
                # read-only. This checked copy is private to the current run.
                target = self.cache / 'tools'
                if not target.exists(): shutil.copytree(exports['tools'], target, symlinks=False)
            self.context = context

    def command(self, command, workdir='/workspace'):
        args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        args += ['--symlink', '/usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                 '--dir', '/home', '--dir', '/home/studio', '--dir', '/etc',
                 '--bind', str(self.worker.store.workspace), '/workspace',
                 '--bind', str(self.cache), '/cache']
        if self.worker.store.owner_type == 'project':
            args += ['--ro-bind', str(self.context['cache'] / 'global/p'), '/packages']
        # PowerShell/.NET resolve the current Unix identity during startup.
        # These public OS records are read-only; shadow, auth and host homes
        # remain absent from the namespace.
        for path in ('/etc/passwd', '/etc/group', '/etc/nsswitch.conf', '/etc/os-release'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        for name, path in self.context['paths'].items():
            args += ['--ro-bind', str(path), '/' + name]
        if self.context.get('rust'):
            args += ['--ro-bind', str(self.context['rust']['prefix']), '/rust']
        if self.context.get('sdkTools') or self.context.get('rust'):
            args += ['--bind', str(self.cache / 'tools'), '/tools']
        if self.context.get('runner'):
            args += ['--ro-bind', str(self.context['runner'].parent), '/pwsh']
        rust_bin = ''
        if self.context.get('rust'):
            rust_bin = '/rust/' + str(self.context['rust']['compiler'].parent)
        args += ['--dir', '/runner', '--ro-bind', str(Path(__file__).parent / 'file_worker.py'), '/runner/file_worker.py',
                 '--ro-bind', str(self.binary), '/runner/codex', '--chdir', workdir, '--clearenv',
                 '--setenv', 'HOME', '/cache/home', '--setenv', 'PATH', '/pwsh:/zig:' + rust_bin + ':/usr/bin:/bin',
                 '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'SDK_ROOT', '/sdk', '--setenv', 'CONTRACT_ROOT', '/contract',
                 '--setenv', 'CARGO_NET_OFFLINE', 'true', '--setenv', 'RUSTUP_TOOLCHAIN', 'studio-pinned',
                 '--setenv', 'ZIG_GLOBAL_CACHE_DIR', '/cache/zig',
                 '--setenv', 'CARGO_HOME', '/cache/cargo', '--setenv', 'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT', '1',
                 '--setenv', 'POWERSHELL_TELEMETRY_OPTOUT', '1']
        return args + command

    async def file(self, name, arguments):
        import json
        from file_worker import Fault
        try:
            if name == 'apply_patch' and self.worker.skill_resources.patch_target(arguments.get('patch', '')):
                return {'success': False, 'error': 'readOnly', 'output': 'Published skill resources are read-only. No patch changes were applied.'}
            if arguments.get('root', 'workspace') == 'workspace':
                relative = self.worker.skill_resources.target(arguments.get('path', '.'))
                if relative is not None:
                    async with self.lock: return await self.worker.skill_resources.read(name, arguments, relative)
        except Fault:
            return {'success': False, 'error': 'fileError', 'output': 'Use a relative path within the selected file root.'}
        if self.worker.store.owner_type == 'skill' and arguments.get('root', 'workspace') != 'workspace':
            return {'success': False, 'error': 'unavailable', 'output': 'Only the selected skill workspace is available.'}
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
