"""Direct tools in the selected workspace with per-run paths and caches."""
import asyncio
import json
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from workspace_context import Workspace
from profile import regular, digest, directory, CODEX_SHA256,CODEX_VERSION


class WorkspaceTools:
    def __init__(self, worker):
        self.worker = worker; self.context = None; self.sdk_ready = False
        self.script_roots = []
        self.lock = asyncio.Lock(); self.initializing = asyncio.Lock()
        self.reader = None

    async def prepare(self, sdk=True):
        async with self.initializing:
            if self.context is not None:
                if sdk: await self.prepare_sdk()
                return
            context = {'paths': {}}
            # The official patch parser is a separate pinned tool, independent
            # of the Claude model engine and its native2.x version.
            patch_version=CODEX_VERSION if self.worker.config['engine'].get('kind') in ('claude-code', 'studio') else self.worker.config['engine']['version']
            binary = Path(self.worker.manifest['r4os']) / 'Toolchains/Codex' / patch_version / 'codex'
            if self.worker.config['engine'].get('kind') == 'studio':
                pass  # Ordinary file/terminal tools do not need a model-agent binary.
            elif self.worker.config['engine'].get('kind') == 'claude-code':
                if digest(regular(binary)) != CODEX_SHA256: raise ValueError('The private file patch utility changed.')
            else:
                from codex_runtime import binary as runtime_binary
                binary = runtime_binary(self.worker.manifest['r4os'], self.worker.config['engine'])
            self.binary = binary
            from skill_scripts import bindings
            from skill_application import Snapshot
            snapshot = (await asyncio.to_thread(Snapshot, self.worker.store.projects)
                if self.worker.config.get('skillAccess',{}).get('entries') else None)
            self.script_roots = await asyncio.to_thread(bindings, self.worker, snapshot)
            if snapshot is not None: await asyncio.to_thread(self.worker.skill_resources.paths, snapshot)
            self.cache = directory(self.worker.store.directory / self.worker.session_id / 'Tools' / self.worker.run_id)
            for name in ('home', 'zig', 'cargo'): directory(self.cache / name)
            self.context = context
            if sdk: await self.prepare_sdk()

    async def prepare_sdk(self):
        if self.sdk_ready or self.worker.store.owner_type == 'skill': return
        from sdk import profile
        context = await asyncio.to_thread(profile, Path(self.worker.manifest['r4os']),
                          self.worker.store.projects, self.worker.config['projectPins'])
        package_link = self.cache / 'zig/p'
        packages = context['cache'] / 'global/p'
        if package_link.is_symlink() and os.readlink(package_link) == '/packages': package_link.unlink()
        if not package_link.exists() and not package_link.is_symlink(): package_link.symlink_to(packages)
        self.context = context; self.sdk_ready = True

    def needs_sdk(self, arguments):
        from image_instructions import ALIAS
        recipe = '/sdk/' + ALIAS
        def component(path):
            if path == recipe or path.startswith(recipe + '/'): return False
            return any(path == '/' + name or path.startswith('/' + name + '/')
                for name in ('sdk','contract','libraries','install','zig','rust','tools','pwsh'))
        root = arguments.get('root','workspace')
        path = arguments.get('path','.')
        if root != 'workspace' and not (root == 'sdk' and (path == ALIAS or path.startswith(ALIAS + '/'))): return True
        paths = [path, *arguments.get('expectedHashes',{})]
        for line in arguments.get('patch','').splitlines():
            for prefix in ('*** Add File: ', '*** Update File: ', '*** Delete File: ', '*** Move to: '):
                if line.startswith(prefix): paths.append(line[len(prefix):])
        return any(component(path) for path in paths)

    def paths(self):
        paths = {'/' + name: path for name, path in self.context['paths'].items()}
        paths.update({'/cache': self.cache, '/runner': Path(__file__).parent,
                      '/runner/codex': self.binary})
        for ident, path in self.script_roots: paths['/skills/' + ident] = path
        from attachment_files import mounts
        for source, target in mounts(self.worker): paths[target] = source
        if self.context.get('rust'): paths['/rust'] = self.context['rust']['prefix']
        exports = self.context.get('sdkTools') or self.context.get('rust')
        if exports: paths['/tools'] = exports['tools']
        if self.context.get('runner'): paths['/pwsh'] = self.context['runner'].parent
        paths.update(self.worker.skill_resources.paths())
        if self.worker.store.owner_type == 'project':
            from image_instructions import ALIAS
            if '/sdk' not in paths: paths['/sdk'] = directory(self.cache / 'recipe-root')
            paths['/sdk/' + ALIAS] = Path(__file__).resolve().parents[2] / 'shared/r4os/image-recipes'
        return paths

    def workspace(self):
        return Workspace(self.worker.store.workspace, self.paths())

    def command(self, command, workdir='.', patch=False):
        context = self.workspace()
        if patch and self.worker.config['engine'].get('kind') == 'studio' and digest(regular(self.binary)) != CODEX_SHA256:
            raise ValueError('The standalone patch utility changed.')
        paths = self.context['paths']
        bins = [self.context['runner'].parent] if self.context.get('runner') else []
        if paths.get('zig'): bins.append(paths['zig'])
        if self.context.get('rust'): bins.append(self.context['rust']['prefix'] / self.context['rust']['compiler'].parent)
        environment = {'HOME': self.cache / 'home', 'PATH': ':'.join(map(str, [*bins, '/usr/local/bin', '/usr/bin', '/bin'])),
            'CARGO_HOME': self.cache / 'cargo', 'ZIG_GLOBAL_CACHE_DIR': self.cache / 'zig',
            'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT': '1', 'POWERSHELL_TELEMETRY_OPTOUT': '1',
            'STUDIO_PATCH_BINARY': self.binary}
        for key, name in [('SDK_ROOT', 'sdk'), ('CONTRACT_ROOT', 'contract'), ('LIBRARIES_ROOT', 'libraries'), ('SDK_INSTALL_ROOT', 'install')]:
            if name in paths: environment[key] = paths[name]
        if '/tools' in context.paths: environment['SDK_TOOLS_ROOT'] = context.paths['/tools']
        if self.context.get('rust'):
            environment.update(RUSTUP_AUTO_INSTALL='0', RUSTUP_HOME=paths['install'] / 'Toolchains/Rust/rustup',
                RUSTUP_TOOLCHAIN=Path(self.context['package']['record']['rust']['toolchain']).name)
        return context.command(command, workdir, environment)

    async def file(self, name, arguments):
        await self.prepare(sdk=self.needs_sdk(arguments))
        # All calls share this lock, including reads, so a read/hash pair observes
        # the preceding Studio write. External administrator edits remain external.
        async with self.lock:
            if name in ('list_directory','read_file','search'):
                return await self.read_file_tool(name,arguments)
            from terminal_group import Group, identity
            proc = await asyncio.create_subprocess_exec(*self.command(['/usr/bin/python3', '-I', '-B', str(Path(__file__).with_name('file_worker.py'))], patch=name == 'apply_patch'),
                       stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                       limit=262144, start_new_session=True)
            original = identity(proc.pid)
            group = Group(proc.pid, original[3] if original else None)
            try:
                output, _ = await asyncio.wait_for(proc.communicate(json.dumps({'tool': name, 'arguments': arguments}).encode()), 30)
                if proc.returncode or len(output) > 196608: raise ValueError()
                return json.loads(output)
            except BaseException:
                await group.stop()
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                raise

    async def read_file_tool(self,name,arguments):
        from terminal_group import Group, identity
        command=self.command(['/usr/bin/python3','-I','-B',str(Path(__file__).with_name('file_worker.py')),'--serve'])
        if self.reader and (self.reader[0]!=command or self.reader[1].returncode is not None): await self.close_reader()
        if self.reader is None:
            proc=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=262144,start_new_session=True)
            original=identity(proc.pid)
            self.reader=(command,proc,Group(proc.pid,original[3] if original else None))
        _,proc,_=self.reader
        try:
            async with asyncio.timeout(30):
                proc.stdin.write(json.dumps({'tool':name,'arguments':arguments}).encode()+b'\n')
                await proc.stdin.drain()
                output=await proc.stdout.readline()
            if not output or len(output)>196608: raise ValueError('The file reader returned no bounded result.')
            return json.loads(output)
        except BaseException:
            await self.close_reader()
            raise

    async def close_reader(self):
        if self.reader is None: return
        _,proc,group=self.reader; self.reader=None
        proc.stdin.close()
        try: await asyncio.wait_for(proc.wait(),.5)
        except asyncio.TimeoutError:
            await group.stop()
            if proc.returncode is None: proc.kill(); await proc.wait()

    async def close(self):
        async with self.lock: await self.close_reader()
