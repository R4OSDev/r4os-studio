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
from build_cache import BuildCache


class Builder:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.context = None; self.process = None; self.stopping = False; self.cache = None
        self.root = folder(store.root / 'Work' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'
        self.written = self.log.stat().st_size if self.log.exists() else 0
        self.capture_truncated = job.get('captureTruncated') if self.log.exists() else False

    def append(self, data):
        # All subprocess paths are virtual. Preparation errors never disclose
        # host paths or component metadata to the model/browser.
        if len(data)>max(0,LIMITS['outputBytes']-self.written) and self.capture_truncated is not True:
            self.capture_truncated=True;self.store.observe(self.job['id'],captureTruncated=True)
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
        executable = {item['path'] for item in receipt['files'] if item.get('executable')}
        for path in (self.root / 'source').rglob('*'):
            if path.is_file(): path.chmod(0o700 if str(path.relative_to(self.root / 'source')) in executable else 0o600)
        from sdk_inputs import read, arguments
        self.inputs = read(self.root / 'source')
        if self.inputs != self.job.get('sdkInputs'):
            raise DevelopmentFault('The captured SDK input selection differs from the original build request.')
        self.sdk_paths, self.sdk_arguments, self.dependencies = arguments(self.inputs, self.root)
        self.catalog_root = '/workspace'
        if self.inputs['development']:
            # Development SDKs contain their own template/module catalog. They
            # are source inputs, not additional project entrypoints.
            excluded = {value for key, value in self.inputs['development'].items() if key != 'profile'}
            def ignore(base, names):
                return [name for name in names if name == '.git' or str((Path(base) / name).relative_to(self.root / 'source')) in excluded]
            shutil.copytree(self.root / 'source', self.root / 'catalog-source', ignore=ignore)
            self.catalog_root = '/catalog-workspace'
        for name in ('home', 'zig', 'zig-local', 'output', 'tools', 'cargo', 'rust-build'): folder(self.root / name)
        self.cache = BuildCache(self.store, self.job)
        # Only this job's exact tool copy is writable. Shared SDK sources and
        # SDK-selected vendor tools remain readonly in the build namespace.
        shutil.copytree(self.context['sdkTools']['tools'], self.root / 'tools', dirs_exist_ok=True)
        native = self.context['sdkTools']['profile']['hosts']['Linux']
        self.inspector = self.context['sdkTools']['tools'] / relative(native['packager'])

    async def update_identity(self, binary, manifest):
        """An optional package capability; ordinary builds retain their behavior."""
        if self.inputs['technical']:
            return {'available': False, 'reason': 'Technical Development builds have no regular SDK-qualified update identity.'}
        source = Path(__file__).with_name('update_identity.zig')
        sdk_source = self.context['paths']['sdk'] / 'r4os/r4u_artifact.zig'
        if not sdk_source.is_file(): return {'available': False, 'reason': 'This SDK has no native update artifact inspector.'}
        target = manifest.get('target')
        if not isinstance(target, str): return {'available': False, 'reason': 'The SDK catalogue has no installation target.'}
        kind = {'library': 'system-library', 'driver': 'driver', 'protocol': 'protocol', 'service': 'service'}.get(self.store.project['template'], 'software')
        data = self.context['package']['profiles']['Build']
        profiles = [(ident, value) for ident, value in data['profiles'].items()
                    if value['language'] == 'Zig' and value['role'] == 'host']
        if len(profiles) != 1:
            return {'available': False, 'reason': 'The SDK does not identify one host-tool profile.'}
        host_id, selected = profiles[0]
        policy = data['codegen'][selected['codegen']]
        if policy.get('optimize') not in policy.get('allowed_optimize_modes', []):
            return {'available': False, 'reason': 'The SDK host-tool optimization policy is unavailable.'}
        key = hash_value({'source': digest(source), 'sdk': self.job['pins']['sdk'], 'zig': self.job['pins']['zig'],
                          'sdkProfiles': self.job['pins']['sdkProfile'], 'hostProfile': host_id, 'codegen': policy})
        inspector = self.context['cache'] / ('r4u-identity-' + key)
        marker = inspector.with_suffix('.json')
        import fcntl
        try:
            with (self.context['cache'] / 'lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if not inspector.is_file() or not marker.is_file() or digest(inspector) != json.loads(marker.read_text()).get('sha256'):
                    from sdk_host import invoke
                    from sdk_package import decode
                    resolved = decode(await asyncio.to_thread(invoke, self.context['runner'], self.context['paths']['sdk'],
                        'Profile.ps1', ['-Action', 'Resolve', '-Profile', host_id,
                        '-ContractRoot', self.context['paths']['contract'], '-LibrariesRoot', self.context['paths']['libraries']],
                        self.context['cache']))
                    if resolved.get('hashes') != self.job['pins']['sdkProfile']['hashes'] or resolved.get('profile') != host_id:
                        raise DevelopmentFault('The SDK host-tool profile binding changed.')
                    await asyncio.to_thread(run, [self.context['paths']['zig'] / 'zig', 'build-exe', '-O' + policy['optimize'],
                        '--dep', 'r4u_artifact', '-Mroot=' + str(source), '-Mr4u_artifact=' + str(sdk_source),
                        '-femit-bin=' + str(inspector)], self.context['env'])
                    save(marker, {'sha256': digest(inspector), 'adapterSha256': digest(source),
                                   'sdkProfile': host_id, 'profileHashes': resolved['hashes']})
            # Existing non-networked build namespace, separate readonly inspector bind.
            self.update_inspector = inspector
            value = json.loads(await self.execute(['/update-inspector', '/output/' + str(binary.relative_to(self.root / 'output')), target, kind], 'both'))
            if (value.get('schema') != 1 or value.get('kind') != manifest.get('kind')
                    or value.get('name', '').casefold() != manifest.get('name', '').casefold()
                    or value.get('version') != manifest.get('module_version')):
                raise DevelopmentFault('Native update identity differs from the SDK manifest.')
            return {'available': True, 'identity': value, 'payloadKind': kind, 'manifest': manifest,
                    'inspectorSha256': digest(inspector), 'adapterSha256': digest(source),
                    'sdkRevision': self.job['pins']['sdk']['revision'], 'sdkHostProfile': host_id,
                    'profileHashes': self.job['pins']['sdkProfile']['hashes']}
        except (OSError, ValueError, DevelopmentFault):
            self.append(b'Native update identity unavailable; ordinary build result is preserved.\n')
            return {'available': False, 'reason': 'This artifact has no qualified native update identity. Use a compatible SDK build.'}

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
        # Only compiler artifacts persist. Sources, outputs, HOME, Cargo config,
        # the cache identity and its host lock stay outside these shared mounts.
        for name in ('zig', 'zig-local', 'rust-build'):
            args += ['--bind', str(self.cache.root / name), '/cache/' + name]
        for path in ('/etc/passwd', '/etc/group', '/etc/nsswitch.conf', '/etc/os-release'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        if getattr(self, 'update_inspector', None): args += ['--ro-bind', str(self.update_inspector), '/update-inspector']
        if self.catalog_root != '/workspace': args += ['--ro-bind', str(self.root / 'catalog-source'), self.catalog_root]
        for name, path in context['paths'].items(): args += ['--ro-bind', str(path), '/' + name]
        args += ['--ro-bind', str(self.context['runner'].parent), '/powershell',
                 '--bind', str(self.root / 'tools'), '/tools']
        args += ['--chdir', '/workspace', '--clearenv', '--setenv', 'HOME', '/cache/home',
            '--setenv', 'PATH', '/powershell:/zig:/usr/bin:/bin', '--setenv', 'LANG', 'C.UTF-8',
            '--setenv', 'ZIG_GLOBAL_CACHE_DIR', '/cache/zig', '--setenv', 'ZIG_LOCAL_CACHE_DIR', '/cache/zig-local',
            '--setenv', 'CARGO_HOME', '/cache/cargo',
            '--setenv', 'CARGO_NET_OFFLINE', 'true', '--setenv', 'RUSTUP_AUTO_INSTALL', '0',
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
        try:
            return await self.build_locked(source)
        finally:
            if self.cache is not None:
                self.cache.close()

    async def build_locked(self, source):
        await self.prepare(source)
        rust = self.store.project['language'] == 'Rust'
        catalog = '/tools/' + self.context['sdkTools']['profile']['hosts']['Linux']['catalog']
        # Catalog discovery already parses manifests and validates their source
        # paths. The R4X plan below supplies the remaining startup/role checks.
        declared = json.loads(await self.execute([catalog, 'catalog', '--root', self.catalog_root], True))
        entries = [item for item in declared['entries'] if item['path'] == self.catalog_root + '/module.R4MF']
        if len(entries) != 1: raise DevelopmentFault('Build input must contain one root project manifest.')
        entry = entries[0]
        if entry.get('name') != self.store.project['moduleName'] or entry.get('language') != self.store.project['language']:
            raise DevelopmentFault('The manifest name or language differs from the project identity.')
        expected_kind = {'library': 'R4L', 'driver': 'R4D', 'protocol': 'R4P'}.get(self.store.project['template'], 'R4X')
        if entry['kind'] != expected_kind: raise DevelopmentFault('The manifest kind differs from the project role.')
        from resource_inputs import collect as collect_resource_inputs
        resource_inputs=collect_resource_inputs(entry,self.store.get(self.job['id'])['source'])
        exported = json.loads(await self.execute([catalog, 'plan', '--manifest', '/workspace/module.R4MF'], True))
        if exported.get('schema') != 1 or not isinstance(exported.get('plan'), dict):
            raise DevelopmentFault('The SDK semantic plan schema is not supported.')
        plan = exported['plan']
        from sdk_profiles import manifest_profile
        ident = manifest_profile(self.context, plan)
        native_profile = ['/powershell/pwsh', '-NoLogo', '-NoProfile', '-File', self.sdk_paths['sdk'] + '/Tools/Profile.ps1',
            '-Action', 'Resolve', '-SdkRoot', self.sdk_paths['sdk'], '-Profile', ident, *self.sdk_arguments]
        self.resolved = json.loads(await self.execute(native_profile, True))
        if (self.resolved.get('profile') != ident or self.resolved.get('technical') is not self.inputs['technical']
                or (not self.inputs['technical'] and self.resolved.get('hashes') != self.job['pins']['sdkProfile']['hashes'])):
            raise DevelopmentFault('The SDK resolved an inconsistent profile or qualification mode.')
        self.development_receipt = None
        if self.inputs['development']:
            selected = self.root / 'source' / self.inputs['development']['profile']
            self.development_receipt = json.loads(selected.read_text())
        self.store.update(self.job['id'], sdkResolution=self.resolved,
                          sdkDevelopment=({'sha256': digest(selected), 'sdkSource': self.development_receipt.get('sdk_source')}
                                          if self.development_receipt else None))
        if expected_kind == 'R4X':
            app_class = {'terminal': 'console', 'desktop': 'gui', 'service': 'service', 'subsystem': 'gui'}[self.store.project['template']]
            if plan.get('app_class') != app_class or (self.store.project['template'] == 'subsystem') != (plan.get('module_role') == 'subsystem'):
                raise DevelopmentFault('The manifest application class differs from the project role.')
            await self.execute([catalog, 'contract-plan', '--manifest', '/workspace/module.R4MF'])
        driver = relative(self.context['capabilities']['project_creation']['rust_builder' if rust else 'c_zig_builder'])
        if not driver.startswith('Tools/'):
            raise DevelopmentFault('The SDK does not declare a host build driver.')
        command = ['/powershell/pwsh', '-NoLogo', '-NoProfile', '-File', self.sdk_paths['sdk'] + '/' + driver,
            '-ProjectRoot', '/workspace', '-SdkRoot', self.sdk_paths['sdk'], *self.sdk_arguments,
            '-ToolsRoot', '/tools', '-ZigRoot', '/zig',
            '-InstallRoot', '/install', '-CacheRoot', '/cache/rust-build', '-OutputRoot', '/output']
        if self.dependencies: command += ['-DependencyRootsJson', json.dumps(self.dependencies)]
        if self.inputs['technical']: command += ['-Technical']
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
        from resource_inventory import inspect as inspect_resource_inventory
        resource_inventory=inspect_resource_inventory(binary,resource_inputs,source)
        resource_inventory['inspectorSha256']=digest(self.inspector)
        resource_inventory['pins']=self.job['pins']
        update_metadata = await self.update_identity(binary, entry)
        self.store.update(self.job['id'], phase='publishing')
        artifact_id = str(uuid.uuid4()); parent = folder(self.store.root / 'Artifacts'); stage = folder(parent / (artifact_id + '.new'))
        shutil.copyfile(binary, stage / name); (stage / name).chmod(0o400)
        files = [{'path': name, 'bytes': binary.stat().st_size, 'sha256': digest(stage / name)}]
        proof_path = self.root / 'output/build.json'
        if (not proof_path.is_file() or proof_path.is_symlink()
                or proof_path.stat().st_size > 2 * 1024 * 1024):
            raise DevelopmentFault('The SDK did not produce a bounded native build receipt.')
        proof = json.loads(proof_path.read_text())
        profile = proof.get('sdk_profile', {})
        expected_profile = {'id': self.resolved['profile'], 'hashes': self.resolved['hashes']}
        if (proof.get('schema') not in (1, 2) or proof.get('status') != 'success'
                or proof.get('technical') is not self.inputs['technical'] or profile.get('technical') is not self.inputs['technical']
                or profile.get('id') != expected_profile.get('id') or profile.get('hashes') != expected_profile.get('hashes')
                or proof.get('module', {}).get('name') != self.store.project['moduleName']
                or proof.get('artifact', {}).get('sha256') != files[0]['sha256']
                or proof.get('artifact', {}).get('bytes') != files[0]['bytes']
                or proof.get('sdk', {}).get('source', {}).get('commit') != self.job['pins']['sdk']['revision']
                or proof.get('contract', {}).get('source', {}).get('commit') != self.job['pins']['contract']['revision']):
            raise DevelopmentFault('The native SDK receipt does not match this profile, artifact and source set.')
        if rust and proof.get('cargo', {}).get('lock_sha256') != digest(source / 'Cargo.lock'):
            raise DevelopmentFault('The SDK Cargo lock receipt differs from the captured project input.')
        proof_format = 'r4os-sdk-profile-build-v1'
        proof['studioResourceInputs']=resource_inputs
        proof['studioResourceInventory']=resource_inventory
        proof['studioSdkInputs'] = self.inputs
        proof['studioSdkResolution'] = self.resolved
        proof['studioDevelopmentReceipt'] = self.development_receipt
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
            'sdkProfile': proof['sdk_profile'],
            'sdkInputs': self.inputs, 'sdkResolution': self.resolved,
            'plan': plan, 'resourceInputs':resource_inputs, 'resourceInventory':resource_inventory, 'updateMetadata': update_metadata, 'inspectorSha256': digest(self.inspector), 'buildProof': build_proof}
        save(stage / 'artifact.json', record)
        with (stage / name).open('rb') as stream: os.fsync(stream.fileno())
        sync(stage); os.rename(stage, parent / artifact_id); sync(parent)
        return self.store.publish(self.job['id'], record)

    async def stop(self):
        self.stopping = True
        if self.process and self.process.returncode is None: self.process.terminate()
