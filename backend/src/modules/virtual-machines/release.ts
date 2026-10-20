import { readFile, writeFile, mkdir, readdir, lstat, link, rm, rename, open } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { VmConfig, VmImage } from '../../../../shared/virtual-machines.js';
import { root, vmPath, validId, VmError } from './paths.js';
import { exec } from './systemd.js';

const instances = join(root, 'Instances');
const journalPath = (id: string) => join(instances, `.release-${id}.json`);
async function sync(path: string) { const fd = await open(path, 'r'); try { await fd.sync(); } finally { await fd.close(); } }
async function store(path: string, value: unknown) {
  const temporary = path + '.tmp';
  await writeFile(temporary, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  await sync(temporary); await rename(temporary, path); await sync(instances);
}
export async function recoverRelease(id: string) {
  const path = vmPath(id), journal = journalPath(id);
  let value;
  try { value = JSON.parse(await readFile(journal, 'utf8')); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
  if (value.schema !== 1 || !validId(value.operation) || !validId(value.nextRevision) || typeof value.previousRevision !== 'string') throw new VmError('The release-change journal requires host maintenance.');
  const config: VmConfig = JSON.parse(await readFile(join(path, 'vm.json'), 'utf8'));
  if (![value.previousRevision, value.nextRevision].includes(config.revision ?? config.imageSha256)) throw new VmError('The release-change journal no longer matches this VM.');
  // Public config and disk always change together. Before exchange this removes
  // the prepared new overlay; after exchange it removes the replaced old overlay.
  await rm(join(instances, `.release-${id}-${value.operation}`), { recursive: true, force: true });
  await rm(journal); await sync(instances);
}
async function clone(source: string, target: string, relative = '') {
  await mkdir(target, { mode: 0o700 });
  for (const entry of await readdir(source)) {
    const name = relative ? relative + '/' + entry : entry;
    if (name === 'vm.json' || name === 'Disks/disk.qcow2') continue;
    const from = join(source, entry), to = join(target, entry), stat = await lstat(from);
    if (stat.isSymbolicLink()) throw new VmError('VM release changes do not support symbolic links in instance data.');
    if (stat.isDirectory()) await clone(from, to, name);
    else if (stat.isFile()) await link(from, to);
    else throw new VmError('VM release changes require regular instance files.');
  }
  await sync(target);
}
export async function replaceRelease(id: string, config: VmConfig, image: VmImage, imageBinary: string) {
  await recoverRelease(id);
  const base = join(root, 'Images', image.id, 'disk.img');
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(base, { highWaterMark: 1024 * 1024 })) hash.update(chunk);
  if (hash.digest('hex') !== image.sha256) throw new VmError('The selected release disk checksum does not match.');
  const operation = randomUUID(), nextRevision = randomUUID();
  const stage = join(instances, `.release-${id}-${operation}`);
  let journaled = false;
  try {
    await clone(vmPath(id), stage);
    await exec(imageBinary, ['create', '-f', 'qcow2', '-F', 'raw', '-b', base, join(stage, 'Disks/disk.qcow2')], { timeout: 30_000 });
    await sync(join(stage, 'Disks/disk.qcow2')); await sync(join(stage, 'Disks'));
    await writeFile(join(stage, 'vm.json'), JSON.stringify({ ...config, imageId: image.id, imageSha256: image.sha256, revision: nextRevision }, null, 2) + '\n', { mode: 0o600 });
    await sync(join(stage, 'vm.json')); await sync(stage);
    await store(journalPath(id), { schema: 1, operation, previousRevision: config.revision ?? config.imageSha256, nextRevision });
    journaled = true;
    await exec('/usr/bin/python3', [fileURLToPath(new URL('../../../../scripts/vm-release-swap.py', import.meta.url)), instances, id, operation], { timeout: 30_000 });
    await sync(instances);
    await recoverRelease(id);
  } catch (error) {
    if (journaled) {
      // The syscall can succeed before its helper reports an fsync/cleanup
      // error. Recognize that committed result after recovery, never reset again.
      const published: VmConfig = JSON.parse(await readFile(join(vmPath(id), 'vm.json'), 'utf8'));
      await recoverRelease(id);
      if (published.revision === nextRevision) return;
    } else await rm(stage, { recursive: true, force: true });
    throw error;
  }
}
