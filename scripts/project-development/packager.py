"""Run exactly the accepted native Packer, readonly inputs and bounded private output."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import stat
import uuid
from contracts import DevelopmentFault, LIMITS, digest, hash_value
from jobs import folder, now
from layout import save, sync
from package_jobs import program, publish
from update_plans import payload

class Packager:
    def __init__(self, store, job):
        self.store, self.job = store, job
        self.root = folder(store.root / 'PackageWork' / job['id'])
        self.log = store.evidence(job['id']) / 'output.log'
        self.written = self.log.stat().st_size if self.log.exists() else 0
        self.stdout_bytes = 0; self.stderr_bytes = 0
        self.process = None; self.stopping = False; self.output_limited = False

    def append(self, data):
        remaining = max(0, LIMITS['outputBytes'] - self.written)
        with self.log.open('ab') as stream:
            stream.write(data[:remaining]); stream.flush()
        self.written += min(len(data), remaining)
        if len(data) > remaining: self.output_limited = True

    def guard(self):
        current = self.store.get(self.job['id'])
        if self.stopping or current['state'] not in ('queued', 'starting', 'running'):
            raise DevelopmentFault('Packaging stopped before its next effect.')

    def verify_inputs(self):
        plan = self.job['updatePlan']
        if hash_value({key: value for key, value in plan.items() if key != 'sha256'}) != plan['sha256']:
            raise DevelopmentFault('The accepted package plan hash changed.')
        for part in plan['payloads']:
            if payload(self.store, part['artifactId']) != part: raise DevelopmentFault('The accepted package input changed.')

    def command(self, arguments):
        args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts']
        for path in ('/usr', '/lib', '/lib64'):
            if Path(path).exists(): args += ['--ro-bind', path, path]
        args += ['--symlink', '/usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                 '--dir', '/etc', '--ro-bind', str(self.root / 'inputs'), '/inputs',
                 '--ro-bind', str(self.root / 'packer'), '/packer', '--bind', str(self.root / 'output'), '/output',
                 '--chdir', '/output', '--clearenv', '--setenv', 'HOME', '/tmp', '--setenv', 'LANG', 'C.UTF-8',
                 '--setenv', 'PATH', '/usr/bin:/bin']
        return args + ['/packer', *arguments]

    def arguments(self):
        plan = self.job['updatePlan']; meta = plan['metadata']
        args = ['--output', '/output/package.R4U', '--package', meta['packageId'], '--version', meta['packageVersion'],
                '--release', meta['targetRelease'], '--title', meta['title'], '--description-file', '/inputs/description.txt']
        for index, part in enumerate(plan['payloads']):
            args += ['--payload', '/inputs/' + str(index) + '.payload|' + part['target'] + '|' + part['kind']]
        for need in plan['requirements']: args += ['--require', need['spec']]
        return args

    async def build(self):
        self.guard(); self.verify_inputs(); binding = program(self.store, self.job)
        inputs = folder(self.root / 'inputs'); output = folder(self.root / 'output')
        if any(inputs.iterdir()) or any(output.iterdir()) or (self.root / 'packer').exists():
            raise DevelopmentFault('Packaging work already exists; it was not replayed.')
        shutil.copyfile(binding['binary'], self.root / 'packer'); (self.root / 'packer').chmod(0o500)
        if digest(self.root / 'packer') != binding['sha256']: raise DevelopmentFault('The accepted Packer changed while copying.')
        for index, part in enumerate(self.job['updatePlan']['payloads']):
            source = self.store.root / 'Artifacts' / part['artifactId'] / part['file']['path']
            target = inputs / (str(index) + '.payload'); shutil.copyfile(source, target); target.chmod(0o400)
            if target.stat().st_size != part['file']['bytes'] or digest(target) != part['file']['sha256']:
                raise DevelopmentFault('A package source changed while freezing.')
        description = inputs / 'description.txt'; description.write_text(self.job['updatePlan']['metadata']['description'], encoding='utf8'); description.chmod(0o400)
        self.verify_inputs(); self.guard()
        self.store.update(self.job['id'], phase='packing')
        args = self.arguments()
        self.process = await asyncio.create_subprocess_exec(*self.command(args), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        async def drain(stream, channel):
            while data := await stream.read(65536):
                if channel == 'stdout': self.stdout_bytes += len(data)
                else: self.stderr_bytes += len(data)
                self.append(('[' + channel + '] ').encode() + data)
                if self.output_limited: raise DevelopmentFault('Packer output exceeded its limit.')
        try:
            await asyncio.gather(drain(self.process.stdout, 'stdout'), drain(self.process.stderr, 'stderr'))
            code = await self.process.wait()
            if code:
                error = DevelopmentFault('Native R4UPack failed. Read the captured output.')
                error.exit_code = code; raise error
        finally:
            if self.process.returncode is None: self.process.kill(); await self.process.wait()
        self.guard(); self.verify_inputs()
        if digest(self.root / 'packer') != binding['sha256']: raise DevelopmentFault('The frozen Packer changed.')
        for index, part in enumerate(self.job['updatePlan']['payloads']):
            if digest(inputs / (str(index) + '.payload')) != part['file']['sha256']: raise DevelopmentFault('A frozen package source changed.')
        path = output / 'package.R4U'; info = path.lstat()
        if path.resolve(strict=True) != path or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 64 < info.st_size <= LIMITS['packageBytes']:
            raise DevelopmentFault('Native package output is missing, linked or exceeds the Studio quota.')
        with path.open('rb') as stream:
            if stream.read(4) != b'R4U2': raise DevelopmentFault('Native packer output is not R4U2.')
        self.guard(); self.store.update(self.job['id'], phase='publishing')
        ident = str(uuid.uuid4()); parent = folder(self.store.root / 'UpdatePackages'); stage = folder(parent / (ident + '.new'))
        shutil.copyfile(path, stage / 'package.R4U'); (stage / 'package.R4U').chmod(0o400)
        checksum = digest(stage / 'package.R4U')
        if checksum != digest(path): raise DevelopmentFault('Package output changed while publishing.')
        record = {'schema': 1, 'id': ident, 'projectId': self.store.id, 'jobId': self.job['id'],
            'plan': self.job['updatePlan'], 'bytes': info.st_size, 'sha256': checksum, 'format': 'R4U2',
            'createdAt': now(), 'nativeExitCode': 0, 'packer': self.job['updatePlan']['packer'],
            'diagnostics': {'jobId': self.job['id'], 'outputBytes': self.written, 'stdoutBytes': self.stdout_bytes, 'stderrBytes': self.stderr_bytes},
            'arguments': args}
        save(stage / 'package.json', record)
        with (stage / 'package.R4U').open('rb') as stream: os.fsync(stream.fileno())
        sync(stage); self.guard(); os.rename(stage, parent / ident); sync(parent)
        # Retain a private publication record if final DB confirmation is missing.
        save(self.root / 'published.json', record)
        result = publish(self.store, self.job['id'], record)
        from package_jobs import artifact
        artifact(self.store, ident)
        shutil.rmtree(self.root)
        return result

    async def stop(self):
        self.stopping = True
        if self.process and self.process.returncode is None:
            try: self.process.terminate()
            except ProcessLookupError: pass
