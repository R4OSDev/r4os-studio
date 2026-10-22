"""Official pinned SDK build paths inside a credential-free execution namespace."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

from contracts import DevelopmentFault, LIMITS, digest, hash_value, relative
from jobs import folder, now
from layout import save, sync
from sdk import profile, run
from templates import BUILD


class Builder:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.context = None; self.process = None; self.stopping = False
        self.root = folder(store.root / 'Work' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'
        self.written = self.log.stat().st_size if self.log.exists() else 0

    def append(self, data):
        # All subprocess paths are virtual. Preparation errors never disclose
        # host paths or component metadata to the model/browser.
        data = data[:max(0, LIMITS['outputBytes'] - self.written)]
        if not data: return
        with self.log.open('ab') as stream: stream.write(data); stream.flush()
        self.written += len(data)

    async def prepare(self, source):
        receipt = self.store.get(self.job['id'])['source']
        if not receipt or receipt['pins'] != self.job['pins']: raise DevelopmentFault('The source receipt is missing or has different project pins.')
        if receipt['sha256'] != hash_value({'files': receipt['files'], 'directories': receipt['directories']}):
            raise DevelopmentFault('The captured source identity is inconsistent.')
        for item in receipt['files']:
            path = source / relative(item['path'])
            if path.resolve(strict=True) != path or path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                raise DevelopmentFault('The captured build input changed. Start a new build.')
        self.context = await asyncio.to_thread(profile, self.store.r4os, self.store.projects, self.job['pins'], self.store.project['language'] == 'Rust')
        shutil.copytree(source, self.root / 'source')
        for path in (self.root / 'source').rglob('*'):
            if path.is_file(): path.chmod(0o600)
        for name in ('home', 'zig', 'output', 'tools', 'cargo'): folder(self.root / name)
        (self.root / 'zig/p').symlink_to('/packages')
        # SDK build scripts are trusted, pinned component files. User build.zig,
        # Build.ps1 and package URLs do not select a different SDK/compiler.
        if self.context.get('rust'):
            shutil.copytree(self.context['rust']['tools'], self.root / 'tools', dirs_exist_ok=True)
        self.inspector = self.context['cache'] / 'r4m-inspector'
        marker = self.inspector.with_suffix('.json')
        import fcntl
        with (self.context['cache'] / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not self.inspector.is_file() or not marker.is_file() or digest(self.inspector) != json.loads(marker.read_text()).get('sha256'):
                await asyncio.to_thread(run, [self.context['paths']['zig'] / 'zig', 'build-exe', '-OReleaseSafe',
                    self.context['paths']['sdk'] / 'Tools/R4XBuilder/src/main.zig', '-femit-bin=' + str(self.inspector)], self.context['env'])
                save(marker, {'sha256': digest(self.inspector)})

    def command(self, command):
        context = self.context
        args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        args += ['--symlink', '/usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                 '--dir', '/etc', '--dir', '/home', '--bind', str(self.root / 'source'), '/workspace',
                 '--bind', str(self.root / 'output'), '/output', '--bind', str(self.root), '/cache',
                 '--ro-bind', str(context['cache'] / 'global/p'), '/packages',
                 '--ro-bind', str(context['tool']), '/catalog', '--ro-bind', str(self.inspector), '/inspector']
        for path in ('/etc/passwd', '/etc/group', '/etc/nsswitch.conf', '/etc/os-release'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        for name, path in context['paths'].items(): args += ['--ro-bind', str(path), '/' + name]
        rust_bin = '/rust/Install/Rust/1.99.0/bin'
        if context.get('rust'):
            rust_bin = '/rust/' + str(context['rust']['compiler'].parent)
            args += ['--ro-bind', str(context['rust']['prefix']), '/rust',
                     '--bind', str(self.root / 'tools'), '/tools']
        args += ['--chdir', '/workspace', '--clearenv', '--setenv', 'HOME', '/cache/home',
            '--setenv', 'PATH', '/zig:' + rust_bin + ':/usr/bin:/bin', '--setenv', 'LANG', 'C.UTF-8',
            '--setenv', 'ZIG_GLOBAL_CACHE_DIR', '/cache/zig', '--setenv', 'CARGO_HOME', '/cache/cargo',
            '--setenv', 'CARGO_NET_OFFLINE', 'true', '--setenv', 'RUSTUP_TOOLCHAIN', 'studio-pinned',
            '--setenv', 'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT', '1', '--setenv', 'POWERSHELL_TELEMETRY_OPTOUT', '1']
        return args + command

    async def execute(self, command, collect=False):
        if self.stopping: raise DevelopmentFault('Build stopped.')
        self.process = await asyncio.create_subprocess_exec(*self.command(command),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        result = bytearray()
        async def drain(stream, capture):
            while True:
                data = await stream.read(65536)
                if not data: break
                self.append(data)
                if capture:
                    if len(result) + len(data) > LIMITS['outputBytes']: raise DevelopmentFault('SDK metadata exceeds the build limit.')
                    result.extend(data)
        try:
            await asyncio.gather(drain(self.process.stdout, bool(collect)), drain(self.process.stderr, collect == 'both'))
            code = await self.process.wait()
            if code:
                error = DevelopmentFault('The SDK build or validation failed. Read the build output.')
                error.exit_code = code
                raise error
            if self.stopping: raise DevelopmentFault('Build stopped.')
            return bytes(result)
        finally:
            if self.process.returncode is None: self.process.kill(); await self.process.wait()
            self.process = None

    async def build(self, source):
        await self.prepare(source)
        rust = self.store.project['language'] == 'Rust'
        catalog = '/tools/ModuleCatalog' if rust else '/catalog'
        if rust:
            catalog = '/tools/' + self.context['rust']['profile']['hosts']['Linux']['catalog']
        await self.execute([catalog, 'validate', '--manifest', '/workspace/module.R4MF'])
        declared = json.loads(await self.execute([catalog, 'catalog', '--root', '/workspace'], True))
        if len(declared['entries']) != 1: raise DevelopmentFault('Build input must contain exactly one project manifest.')
        entry = declared['entries'][0]
        if entry.get('name') != self.store.project['moduleName'] or entry.get('language') != self.store.project['language']:
            raise DevelopmentFault('The manifest name or language differs from the project identity.')
        expected_kind = {'library': 'R4L', 'driver': 'R4D', 'protocol': 'R4P'}.get(self.store.project['template'], 'R4X')
        if entry['kind'] != expected_kind: raise DevelopmentFault('The manifest kind differs from the project role.')
        plan = None
        if expected_kind == 'R4X':
            exported = json.loads(await self.execute([catalog, 'plan', '--manifest', '/workspace/module.R4MF'], True))
            if exported.get('schema') != 1 or not isinstance(exported.get('plan'), dict):
                raise DevelopmentFault('The SDK semantic plan schema is not supported.')
            plan = exported['plan']
            app_class = {'terminal': 'console', 'desktop': 'gui', 'service': 'service', 'subsystem': 'gui'}[self.store.project['template']]
            if plan.get('app_class') != app_class or (self.store.project['template'] == 'subsystem') != (plan.get('module_role') == 'subsystem'):
                raise DevelopmentFault('The manifest application class differs from the project role.')
            await self.execute([catalog, 'contract-plan', '--manifest', '/workspace/module.R4MF'])
        if rust:
            command = ['/rust/PowerShell/pwsh', '-NoLogo', '-NoProfile', '-File', '/sdk/Tools/Build-RustModule.ps1',
                '-ProjectRoot', '/workspace', '-SdkRoot', '/sdk', '-ContractRoot', '/contract', '-ToolsRoot', '/tools',
                '-InstallRoot', '/rust/Install', '-CacheRoot', '/cache/rust-build', '-OutputRoot', '/output']
            if self.context.get('sdkTools'): command += ['-ZigRoot', '/zig']
        else:
            (self.root / 'source/build.zig').write_text(BUILD)
            pin = self.job['pins']['sdk']
            (self.root / 'source/build.zig.zon').write_text('.{ .name = .r4os_studio_project, .version = "0.1.0", '
                '.fingerprint = 0x17b105fe7653a449, .minimum_zig_version = "0.16.0", .dependencies = .{ .r4os_sdk = .{ '
                '.url = "https://github.com/R4OSDev/r4os-sdk/archive/' + pin['revision'] + '.tar.gz", .hash = "' + pin['zigPackageHash'] + '" } }, .paths = .{""} }\n')
            command = ['/zig/zig', 'build', '--prefix', '/output', '--summary', 'all']
        self.store.update(self.job['id'], phase='compiling')
        await self.execute(command)
        name = self.store.project['moduleName'] + '.' + expected_kind
        candidates = [p for p in (self.root / 'output').rglob(name) if p.is_file() and not p.is_symlink()]
        if len(candidates) != 1: raise DevelopmentFault('The SDK did not produce one fresh module artifact.')
        binary = candidates[0]
        if binary.resolve() != binary.absolute() or binary.stat().st_size > LIMITS['packageBytes']:
            raise DevelopmentFault('Invalid or oversized module artifact.')
        result = await self.execute(['/inspector', '--inspect', '/output/' + str(binary.relative_to(self.root / 'output'))], 'both')
        expected_class = {'terminal': 'console', 'desktop': 'gui', 'service': 'service', 'subsystem': 'gui'}.get(self.store.project['template'])
        if ('kind=' + expected_kind.lower()).encode() not in result or (expected_class and ('r4x.class=' + expected_class).encode() not in result):
            raise DevelopmentFault('The produced container does not match its manifest identity.')
        self.store.update(self.job['id'], phase='publishing')
        artifact_id = str(uuid.uuid4()); parent = folder(self.store.root / 'Artifacts'); stage = folder(parent / (artifact_id + '.new'))
        shutil.copyfile(binary, stage / name); (stage / name).chmod(0o400)
        files = [{'path': name, 'bytes': binary.stat().st_size, 'sha256': digest(stage / name)}]
        if rust:
            proof_path = self.root / 'output/build.json'
            if proof_path.stat().st_size > 2 * 1024 * 1024: raise DevelopmentFault('The SDK build receipt exceeds the limit.')
            proof = json.loads(proof_path.read_text())
            if (proof.get('schema') not in (1, 2) or proof.get('status') != 'success' or proof.get('technical') is not False
                or proof['module']['name'] != self.store.project['moduleName']
                or proof['artifact']['sha256'] != files[0]['sha256']
                or proof['sdk']['source']['commit'] != self.job['pins']['sdk']['revision']
                or proof['contract']['source']['commit'] != self.job['pins']['contract']['revision']
                or proof['cargo']['lock_sha256'] != digest(source / 'Cargo.lock')):
                raise DevelopmentFault('The SDK build receipt does not match this artifact and its pinned inputs.')
            proof_format = 'r4os-sdk-rust-build-v1'
        else:
            proof = {'schema': 1, 'interface': 'r4os-studio-sdk-build', 'status': 'success',
                'manifest': entry, 'plan': plan, 'pins': self.job['pins'], 'command': command,
                'containerInspection': result.decode('utf-8', errors='replace'),
                'artifact': files[0], 'sourceSha256': self.store.get(self.job['id'])['source']['sha256']}
            proof_format = 'r4os-studio-sdk-build-v1'
        save(stage / 'build-proof.json', proof)
        build_proof = {'format': proof_format, 'sha256': digest(stage / 'build-proof.json'),
                       'bytes': (stage / 'build-proof.json').stat().st_size}
        # Non-module resources remain source inputs; R4MF resources packed by the
        # official SDK are checked by its container inspector.
        record = {'id': artifact_id, 'projectId': self.store.id, 'buildId': self.job['id'],
            'sourceSha256': self.store.get(self.job['id'])['source']['sha256'],
            'manifestSha256': self.store.get(self.job['id'])['source']['manifestSha256'],
            'packageSha256': hash_value(files), 'kind': expected_kind, 'role': self.store.project['template'],
            'entry': name, 'files': files, 'createdAt': now(), 'pins': self.job['pins'],
            'plan': plan, 'inspectorSha256': digest(self.inspector), 'buildProof': build_proof}
        save(stage / 'artifact.json', record)
        with (stage / name).open('rb') as stream: os.fsync(stream.fileno())
        sync(stage); os.rename(stage, parent / artifact_id); sync(parent)
        return self.store.publish(self.job['id'], record)

    async def stop(self):
        self.stopping = True
        if self.process and self.process.returncode is None: self.process.terminate()
