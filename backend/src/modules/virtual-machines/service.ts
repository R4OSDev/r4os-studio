import { mkdir, readFile, writeFile, rename, readdir, rm, lstat, open, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { totalmem } from 'node:os';
import type { VirtualMachine, VmConfig, VmImage, VmInput, VmState, VmReleaseChange, VmResetInput } from '../../../../shared/virtual-machines.js';
import { networkAvailable } from './network.js';
import { recoverRelease, replaceRelease } from './release.js';
import { recoverReset, resetDisks, completedReset } from './reset.js';
import { activeTool } from '../components/tools.js';
import { root, runtimePath, vmPath, validId, VmError } from './paths.js';
import { exec, unitState, control } from './systemd.js';
import { qmp } from './qmp.js';
import { reservedExchangeName } from './exchange-identity.js';
import { shareFiles, validFilename } from './share.js';
import { finishShare, shareState } from './share-sync.js';

async function atomic(path: string, data: unknown) {
  const staging = `${path}.${randomUUID()}.tmp`;
  await writeFile(staging, JSON.stringify(data, null, 2) + '\n', { mode: 0o600 });
  await rename(staging, path);
}
export function compareImages(a: VmImage, b: VmImage) {
  const av = a.version.split('.').map(Number), bv = b.version.split('.').map(Number);
  return bv[0] - av[0] || bv[1] - av[1] || bv[2] - av[2] || a.id.localeCompare(b.id);
}
export async function images(): Promise<VmImage[]> {
  await mkdir(join(root, 'Images'), { recursive: true, mode: 0o700 });
  const result: VmImage[] = [];
  for (const entry of await readdir(join(root, 'Images'), { withFileTypes: true })) {
    if (!entry.isDirectory() || !/^[a-zA-Z0-9_.-]{1,100}$/.test(entry.name) || entry.name.startsWith('.')) continue;
    try {
      const image = JSON.parse(await readFile(join(root, 'Images', entry.name, 'image.json'), 'utf8')) as VmImage;
      const disk = await lstat(join(root, 'Images', entry.name, 'disk.img'));
      if (image.schema === 1 && image.id === entry.name && image.variant === 'full' && image.architecture === 'x86_64'
        && image.disk === 'disk.img' && /^\d+\.\d+\.\d+$/.test(image.version) && /^[a-f0-9]{64}$/.test(image.sha256)
        && disk.isFile() && !disk.isSymbolicLink()) result.push(image);
    } catch { /* incomplete imports are not offered */ }
  }
  return result.sort(compareImages);
}

export async function defaultImage(local: VmImage[]): Promise<VmImage | undefined> {
  try {
    const profile = JSON.parse(await readFile(join(root, 'Profiles/versions.json'), 'utf8'));
    if (profile.schema !== 1) return;
    const selected = profile.defaults?.r4os;
    return local.find((image) => image.id === selected?.id && image.sha256 === selected.sha256);
  } catch (error) {
    // Legacy installations retain their previous choice until a component profile exists.
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return local[0];
    return;
  }
}

export class VmManager {
  private recovery = new Map<string, Promise<void>>();
  private verifiedImages = new Map<string, string>();
  private locks = new Map<string, Promise<unknown>>();
  async locked<T>(id: string, work: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(id) ?? Promise.resolve();
    const current = previous.catch(() => {}).then(work); this.locks.set(id, current);
    try { return await current; } finally { if (this.locks.get(id) === current) this.locks.delete(id); }
  }
  async available() {
    try {
      await exec((await activeTool('qemu')).binary, ['--version'], { timeout: 5000 });
      await exec('/usr/bin/systemctl', ['cat', 'r4os-studio-vm@.service'], { timeout: 5000 }); return true;
    } catch { return false; }
  }
  async config(id: string): Promise<VmConfig> {
    const path = vmPath(id);
    let pending = this.recovery.get(id);
    if (!pending) { pending = recoverReset(id).then(() => recoverRelease(id)); this.recovery.set(id, pending); void pending.catch(() => this.recovery.delete(id)); }
    await pending;
    try { return JSON.parse(await readFile(join(path, 'vm.json'), 'utf8')); }
    catch { throw new VmError('Virtual machine not found.', 404); }
  }
  async get(id: string): Promise<VirtualMachine> {
    const config = await this.config(id);
    const unit = await unitState(id);
    let state: VmState = 'stopped';
    if (unit.ActiveState === 'failed') state = 'failed';
    else if (unit.ActiveState === 'deactivating') state = 'stopping';
    else if (['active', 'activating'].includes(unit.ActiveState)) {
      state = 'starting';
      try { const status = await qmp(id, 'query-status'); state = status.running ? 'running' : 'paused'; } catch { /* booting */ }
    }
    const sync = await shareState(vmPath(id)).catch(() => ({ pending: true, error: 'The exchange sync state is invalid. Inspect it or explicitly reset the Exchange partition.', lastSyncedAt: undefined }));
    return { ...config, networkEnabled: config.networkEnabled ?? false, state, shareSync: sync && { pending: sync.pending, error: sync.error, lastSyncedAt: sync.lastSyncedAt }, shareMode: 'fat32-persistent', sharePath: join(vmPath(id), 'Exchange/Share'),
      ...(state === 'failed' ? { error: 'The VM stopped with an error. Check Logs.' } : {}) };
  }
  async list() {
    await mkdir(join(root, 'Instances'), { recursive: true, mode: 0o700 });
    const entries = await readdir(join(root, 'Instances'));
    const result = await Promise.all(entries.filter(validId).map((id) => this.get(id)));
    return result.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }
  async create(input: VmInput) {
    return this.locked('create', async () => {
      if ((await this.list()).length >= 32) throw new VmError('The workspace is limited to 32 virtual machines.');
      if (!input.name.trim()) throw new VmError('Enter a virtual machine name.', 400);
      const networkEnabled = input.networkEnabled ?? true;
      if (networkEnabled && !await networkAvailable()) throw new VmError('VM network host support is not installed.');
      const local = await images();
      const image = input.imageId ? local.find((i) => i.id === input.imageId) : await defaultImage(local);
      if (!image) throw new VmError('Select an installed default release under Updates → R4OS Releases before creating a VM.');
      const base = join(root, 'Images', image.id, 'disk.img');
      const stat = await lstat(base);
      const signature = `${image.sha256}:${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}`;
      if (this.verifiedImages.get(image.id) !== signature && !(image.diskSizeBytes === stat.size && image.diskMtimeMs === Math.trunc(stat.mtimeMs))) {
        const hash = createHash('sha256');
        for await (const chunk of createReadStream(base, { highWaterMark: 1024 * 1024 })) hash.update(chunk);
        if (hash.digest('hex') !== image.sha256) throw new VmError('The base image checksum does not match.');
        this.verifiedImages.set(image.id, signature);
      }
      const id = randomUUID(), directory = join(root, 'Instances', `.creating-${id}`);
      for (const part of ['Disks', 'Exchange/Share', 'Logs']) await mkdir(join(directory, part), { recursive: true, mode: 0o700 });
      try {
        await exec((await activeTool('qemu')).imageBinary!, ['create', '-f', 'qcow2', '-F', 'raw', '-b', base, join(directory, 'Disks/disk.qcow2')], { timeout: 30_000 });
        const config: VmConfig = { schema: 1, id, name: input.name.trim(), imageId: image.id, imageSha256: image.sha256,
          cpus: input.cpus, memoryMiB: input.memoryMiB, networkEnabled, revision: randomUUID(), createdAt: new Date().toISOString() };
        await atomic(join(directory, 'vm.json'), config);
        await rename(directory, vmPath(id));
      } catch (error) { await rm(directory, { recursive: true, force: true }); throw error; }
      return this.get(id);
    });
  }
  async stopped(id: string) {
    const vm = await this.get(id);
    if (!['stopped', 'failed'].includes(vm.state)) throw new VmError('Stop the VM before changing its settings or exchange folder.');
    return vm;
  }
  async update(id: string, input: VmInput) {
    return this.locked(id, async () => {
      await this.stopped(id); const config = await this.config(id);
      if (!input.name.trim()) throw new VmError('Enter a virtual machine name.', 400);
      const networkEnabled = input.networkEnabled ?? config.networkEnabled ?? false;
      if (networkEnabled && !await networkAvailable()) throw new VmError('VM network host support is not installed.');
      await atomic(join(vmPath(id), 'vm.json'), { ...config, networkEnabled, revision: randomUUID(), name: input.name.trim(), cpus: input.cpus, memoryMiB: input.memoryMiB });
      return this.get(id);
    });
  }
  async changeRelease(id: string, input: VmReleaseChange) {
    return this.locked('admission', () => this.locked(id, async () => {
      const vm = await this.stopped(id), config = await this.config(id);
      if (input.confirm !== true) throw new VmError('Confirm the release change.', 400);
      // Retries and selecting the current release never erase guest changes.
      if (config.imageId === input.imageId && config.imageSha256 === input.imageSha256) return vm;
      if ((config.revision ?? config.imageSha256) !== input.expectedRevision || config.imageId !== input.expectedImageId || config.imageSha256 !== input.expectedImageSha256)
        throw new VmError('The VM changed after confirmation. Review its current release and confirm again.');
      const image = (await images()).find((image) => image.id === input.imageId && image.sha256 === input.imageSha256);
      if (!image) throw new VmError('The selected release is no longer available locally.');
      if (vm.shareSync?.pending) await finishShare(vmPath(id));
      await replaceRelease(id, config, image, (await activeTool('qemu')).imageBinary!);
      return this.get(id);
    }));
  }
  async action(id: string, action: string) {
    // Global admission lock includes concurrent starts of different VMs.
    return this.locked('admission', () => this.locked(id, async () => {
      const vm = await this.get(id);
      if (action === 'start') {
        await this.stopped(id);
        const active = (await this.list()).filter((v) => !['stopped', 'failed'].includes(v.state));
        if (active.reduce((sum, v) => sum + v.memoryMiB, vm.memoryMiB) > totalmem() / 1024 / 1024 * .75)
          throw new VmError('The running VMs would exceed 75% of host memory.');
        await control(id, 'start');
      } else if (action === 'sync-exchange') { await this.stopped(id); await finishShare(vmPath(id)); }
      else if (action === 'force-stop') await control(id, 'stop');
      else {
        if (!['running', 'paused'].includes(vm.state)) throw new VmError('The VM is not running.');
        await qmp(id, action === 'shutdown' ? 'system_powerdown' : 'system_reset');
      }
      return this.get(id);
    }));
  }
  async reset(id: string, input: VmResetInput, leaseGuard: () => void) {
    return this.locked('admission', () => this.locked(id, async () => {
      await recoverReset(id);
      await recoverRelease(id);
      if (await completedReset(id, input)) return this.get(id);
      const config = await this.config(id);
      const stopped = async () => {
        leaseGuard();
        const { stdout } = await exec('/usr/bin/systemctl', ['show', `r4os-studio-vm@${id}.service`, '--property=ActiveState,MainPID,ControlPID'], { timeout: 5000 });
        const state = Object.fromEntries(stdout.trim().split('\n').map((line) => line.split('=')));
        if (!['inactive', 'failed'].includes(state.ActiveState) || state.MainPID !== '0' || state.ControlPID !== '0')
          throw new VmError('Stop the VM and wait for its export worker before resetting it.');
        leaseGuard();
      };
      await stopped();
      if (input.kind === 'system') {
        const share = await shareState(vmPath(id));
        if (share?.pending || share?.error) await finishShare(vmPath(id));
        const settled = await shareState(vmPath(id));
        if (settled?.pending || settled?.error) throw new VmError('Resolve the pending Exchange sync before resetting the system disks.');
      }
      await resetDisks(id, config, input, (await activeTool('qemu')).imageBinary!, stopped, leaseGuard);
      return this.get(id);
    }));
  }
  async remove(id: string) {
    return this.locked(id, async () => { await this.stopped(id); await rm(vmPath(id), { recursive: true }); });
  }
  async files(id: string) { await this.config(id); return (await shareFiles(join(vmPath(id), 'Exchange/Share'))).filter((file) => !reservedExchangeName(file.name)); }
  async upload(id: string, name: string, content: string) {
    return this.locked(id, async () => {
      await this.stopped(id);
      if (!validFilename(name) || reservedExchangeName(name)) throw new VmError('Use an ASCII filename with letters, digits, dots, underscores or hyphens.', 400);
      const data = Buffer.from(content, 'base64');
      if (data.length > 8 * 1024 * 1024) throw new VmError('Files are limited to 8 MiB per upload.', 400);
      const files = await this.files(id);
      if (files.some((f) => f.name.toLowerCase() === name.toLowerCase())) throw new VmError('A file with this name already exists.');
      if (files.length >= 128 || files.reduce((sum, f) => sum + f.size, data.length) > 96 * 1024 * 1024) throw new VmError('The exchange folder is full.');
      await writeFile(join(vmPath(id), 'Exchange/Share', name), data, { mode: 0o600, flag: 'wx' });
    });
  }
  async removeFile(id: string, name: string) {
    return this.locked(id, async () => {
      await this.stopped(id); if (!validFilename(name) || reservedExchangeName(name)) throw new VmError('Invalid filename.', 400);
      await rm(join(vmPath(id), 'Exchange/Share', name));
    });
  }
  async log(id: string, name: 'serial' | 'qemu') {
    await this.config(id);
    try {
      const file = await open(join(vmPath(id), `Logs/${name}.log`), 'r');
      try { const stat = await file.stat(); const buffer = Buffer.alloc(Math.min(stat.size, 128 * 1024));
        const result = await file.read(buffer, 0, buffer.length, Math.max(0, stat.size - buffer.length)); return buffer.subarray(0, result.bytesRead).toString();
      } finally { await file.close(); }
    } catch { return ''; }
  }
  async screen(id: string, maxBytes?: number) {
    await this.config(id); const path = join(runtimePath(id), `screen-${randomUUID()}.png`);
    try { await qmp(id, 'screendump', { filename: path, format: 'png' });
      if (maxBytes !== undefined && (await stat(path)).size > maxBytes) throw new VmError('The VM screenshot exceeds its image budget.');
      return await readFile(path); }
    finally { await rm(path, { force: true }); }
  }
}
