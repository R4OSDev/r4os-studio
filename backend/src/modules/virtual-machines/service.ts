import { mkdir, readFile, writeFile, rename, readdir, rm, lstat, open } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { totalmem } from 'node:os';
import type { VirtualMachine, VmConfig, VmImage, VmInput, VmState } from '../../../../shared/virtual-machines.js';
import { root, runtimePath, vmPath, validId, VmError } from './paths.js';
import { exec, unitState, control } from './systemd.js';
import { qmp } from './qmp.js';
import { shareFiles, validFilename } from './share.js';

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

export class VmManager {
  private verifiedImages = new Map<string, string>();
  private locks = new Map<string, Promise<unknown>>();
  async locked<T>(id: string, work: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(id) ?? Promise.resolve();
    const current = previous.catch(() => {}).then(work); this.locks.set(id, current);
    try { return await current; } finally { if (this.locks.get(id) === current) this.locks.delete(id); }
  }
  async available() {
    try {
      await exec('/usr/bin/qemu-system-x86_64', ['--version'], { timeout: 5000 });
      await exec('/usr/bin/systemctl', ['cat', 'r4os-studio-vm@.service'], { timeout: 5000 }); return true;
    } catch { return false; }
  }
  async config(id: string): Promise<VmConfig> {
    const path = vmPath(id);
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
    return { ...config, state, shareMode: 'fat32-snapshot', sharePath: join(vmPath(id), 'Exchange/Share'),
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
      const local = await images();
      const image = input.imageId ? local.find((i) => i.id === input.imageId) : local[0];
      if (!image) throw new VmError('No verified Full image is available. Import a release on the host first.');
      const base = join(root, 'Images', image.id, 'disk.img');
      const stat = await lstat(base);
      const signature = `${image.sha256}:${stat.size}:${stat.mtimeMs}:${stat.ctimeMs}`;
      if (this.verifiedImages.get(image.id) !== signature && !(image.diskSizeBytes === stat.size && image.diskMtimeMs === Math.trunc(stat.mtimeMs))) {
        const hash = createHash('sha256');
        for await (const chunk of createReadStream(base)) hash.update(chunk);
        if (hash.digest('hex') !== image.sha256) throw new VmError('The base image checksum does not match.');
        this.verifiedImages.set(image.id, signature);
      }
      const id = randomUUID(), directory = join(root, 'Instances', `.creating-${id}`);
      for (const part of ['Disks', 'Exchange/Share', 'Logs']) await mkdir(join(directory, part), { recursive: true, mode: 0o700 });
      try {
        await exec('/usr/bin/qemu-img', ['create', '-f', 'qcow2', '-F', 'raw', '-b', base, join(directory, 'Disks/disk.qcow2')], { timeout: 30_000 });
        const config: VmConfig = { schema: 1, id, name: input.name.trim(), imageId: image.id, imageSha256: image.sha256,
          cpus: input.cpus, memoryMiB: input.memoryMiB, createdAt: new Date().toISOString() };
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
      await atomic(join(vmPath(id), 'vm.json'), { ...config, name: input.name.trim(), cpus: input.cpus, memoryMiB: input.memoryMiB });
      return this.get(id);
    });
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
      } else if (action === 'force-stop') await control(id, 'stop');
      else {
        if (!['running', 'paused'].includes(vm.state)) throw new VmError('The VM is not running.');
        await qmp(id, action === 'shutdown' ? 'system_powerdown' : 'system_reset');
      }
      return this.get(id);
    }));
  }
  async remove(id: string) {
    return this.locked(id, async () => { await this.stopped(id); await rm(vmPath(id), { recursive: true }); });
  }
  async files(id: string) { await this.config(id); return shareFiles(join(vmPath(id), 'Exchange/Share')); }
  async upload(id: string, name: string, content: string) {
    return this.locked(id, async () => {
      await this.stopped(id);
      if (!validFilename(name)) throw new VmError('Use an ASCII filename with letters, digits, dots, underscores or hyphens.', 400);
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
      await this.stopped(id); if (!validFilename(name)) throw new VmError('Invalid filename.', 400);
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
  async screen(id: string) {
    await this.config(id); const path = join(runtimePath(id), `screen-${randomUUID()}.png`);
    try { await qmp(id, 'screendump', { filename: path, format: 'png' }); return await readFile(path); }
    finally { await rm(path, { force: true }); }
  }
}
