import { readFile, writeFile, mkdir, readdir, lstat, link, rm, open, realpath, statfs } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { VmConfig, VmImage } from '../../../../shared/virtual-machines.js';
import { root, vmPath, validId, VmError } from './paths.js';
import { exec } from './systemd.js';
import { privateDirectory, readJournal, saveJournal } from './journal.js';

export interface ReleasePlan {
  batchId: string; requestId: string; operation: string; nextRevision: string;
  expectedRevision: string; expectedImageId: string; expectedImageSha256: string;
  imageId: string; imageSha256: string;
}
interface ReleaseReceipt extends ReleasePlan { schema: 1; vmId: string; state: 'preparing' | 'aborted' | 'complete' }
export interface VerifiedRelease { assert: () => Promise<void> }
export async function releaseStagingSpace() {
  const space = await statfs(instances);
  if (space.bavail * space.bsize < 64 * 1024 * 1024) throw new VmError('At least 64 MiB of free staging space is required.');
}
const imagePath = (image: VmImage) => join(root, 'Images', image.id, 'disk.img');
const signature = (s: { dev: bigint; ino: bigint; size: bigint; mtimeNs: bigint; ctimeNs: bigint }) => `${s.dev}:${s.ino}:${s.size}:${s.mtimeNs}:${s.ctimeNs}`;
export async function verifyReleaseImage(image: VmImage): Promise<VerifiedRelease> {
  const path = imagePath(image);
  if (await realpath(path) !== path) throw new VmError('The selected release image is linked.');
  const file = await open(path, 'r');
  try {
    const before = await file.stat({ bigint: true }), hash = createHash('sha256');
    if (!before.isFile()) throw new VmError('Invalid release image.');
    for await (const chunk of file.createReadStream({ highWaterMark: 1024 * 1024, autoClose: false })) hash.update(chunk);
    if (hash.digest('hex') !== image.sha256) throw new VmError('The selected release disk checksum does not match.');
    const key = signature(before);
    const assert = async () => {
      const current = await lstat(path, { bigint: true });
      if (!current.isFile() || current.isSymbolicLink() || signature(current) !== key || await realpath(path) !== path)
        throw new VmError('The verified release image changed. Remaining targets were held.');
    };
    if (signature(await file.stat({ bigint: true })) !== key) throw new VmError('The selected image changed during checksum verification.');
    await assert(); return { assert };
  } finally { await file.close(); }
}
export async function releaseReceipt(id: string, plan: ReleasePlan) {
  if (!validId(id) || !validId(plan.requestId) || !validId(plan.batchId) || !validId(plan.operation) || !validId(plan.nextRevision)) throw new VmError('Invalid release request identity.', 400);
  const receipt = await readJournal<ReleaseReceipt>(join(vmPath(id), 'ReleaseRequests', plan.requestId + '.json'));
  if (receipt && (receipt.schema !== 1 || receipt.vmId !== id || !['preparing', 'aborted', 'complete'].includes(receipt.state)
    || Object.entries(plan).some(([key, value]) => receipt[key as keyof ReleasePlan] !== value)))
    throw new VmError('This original release receipt belongs to another operation.');
  return receipt;
}
export async function recoverReleasePlan(id: string, plan: ReleasePlan) {
  await recoverRelease(id);
  const receipt = await releaseReceipt(id, plan);
  if (receipt?.state !== 'preparing') return receipt;
  const config: VmConfig = JSON.parse(await readFile(join(vmPath(id), 'vm.json'), 'utf8'));
  // Only while holding the original VM maintenance lease: a preparation that
  // never published its swap journal cannot have committed the atomic exchange.
  if ((config.revision ?? config.imageSha256) === plan.expectedRevision && config.imageId === plan.expectedImageId
    && config.imageSha256 === plan.expectedImageSha256) {
    await rm(join(instances, `.release-${id}-${plan.operation}`), { recursive: true, force: true });
    const aborted = { ...receipt, state: 'aborted' as const };
    await saveJournal(join(vmPath(id), 'ReleaseRequests', plan.requestId + '.json'), aborted);
    return aborted;
  }
  return receipt;
}

const instances = join(root, 'Instances');
const journalPath = (id: string) => join(instances, `.release-${id}.json`);
async function sync(path: string) { const fd = await open(path, 'r'); try { await fd.sync(); } finally { await fd.close(); } }
export async function recoverRelease(id: string) {
  const path = vmPath(id), journal = journalPath(id);
  let value;
  try { value = JSON.parse(await readFile(journal, 'utf8')); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
  if (value.schema !== 1 || !validId(value.operation) || !validId(value.nextRevision) || typeof value.previousRevision !== 'string') throw new VmError('The release-change journal requires host maintenance.');
  const config: VmConfig = JSON.parse(await readFile(join(path, 'vm.json'), 'utf8'));
  if (![value.previousRevision, value.nextRevision].includes(config.revision ?? config.imageSha256)) throw new VmError('The release-change journal no longer matches this VM.');
  if (value.plan) {
    const receipt = await releaseReceipt(id, value.plan);
    if (!receipt || value.plan.operation !== value.operation || value.plan.nextRevision !== value.nextRevision
      || value.plan.expectedRevision !== value.previousRevision) throw new VmError('The release commit has no matching original receipt.');
    await saveJournal(join(path, 'ReleaseRequests', value.plan.requestId + '.json'), { ...receipt, state: config.revision === value.nextRevision ? 'complete' : 'aborted' });
  }
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
export async function replaceRelease(id: string, config: VmConfig, image: VmImage, imageBinary: string,
  options?: { plan: ReleasePlan; verified: VerifiedRelease; beforeCommit: () => Promise<void> }) {
  await recoverRelease(id);
  const base = imagePath(image), plan = options?.plan;
  if (plan) {
    const previous = await releaseReceipt(id, plan);
    if (previous?.state === 'complete') return;
    if (previous) throw new VmError('This release request was already prepared. Inspect its original outcome before continuing.');
    if (plan.expectedRevision !== (config.revision ?? config.imageSha256) || plan.expectedImageId !== config.imageId
      || plan.expectedImageSha256 !== config.imageSha256 || plan.imageId !== image.id || plan.imageSha256 !== image.sha256)
      throw new VmError('The original release plan changed.');
  }
  if (options) await options.verified.assert();
  else {
    const hash = createHash('sha256');
    for await (const chunk of createReadStream(base, { highWaterMark: 1024 * 1024 })) hash.update(chunk);
    if (hash.digest('hex') !== image.sha256) throw new VmError('The selected release disk checksum does not match.');
  }
  await releaseStagingSpace();
  const operation = plan?.operation ?? randomUUID(), nextRevision = plan?.nextRevision ?? randomUUID();
  const stage = join(instances, `.release-${id}-${operation}`);
  const receipt = plan && { ...plan, schema: 1 as const, vmId: id, state: 'preparing' as const };
  if (receipt) {
    await privateDirectory(join(vmPath(id), 'ReleaseRequests'));
    await saveJournal(join(vmPath(id), 'ReleaseRequests', receipt.requestId + '.json'), receipt);
  }
  let journaled = false;
  try {
    await clone(vmPath(id), stage);
    await exec(imageBinary, ['create', '-f', 'qcow2', '-F', 'raw', '-b', base, join(stage, 'Disks/disk.qcow2')], { timeout: 30_000 });
    await sync(join(stage, 'Disks/disk.qcow2')); await sync(join(stage, 'Disks'));
    await writeFile(join(stage, 'vm.json'), JSON.stringify({ ...config, imageId: image.id, imageSha256: image.sha256, revision: nextRevision, systemGeneration: nextRevision }, null, 2) + '\n', { mode: 0o600 });
    await sync(join(stage, 'vm.json')); await sync(stage);
    await saveJournal(journalPath(id), { schema: 1, operation, previousRevision: config.revision ?? config.imageSha256, nextRevision, ...(plan ? { plan } : {}) });
    journaled = true;
    await options?.verified.assert(); await options?.beforeCommit();
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
    } else {
      await rm(stage, { recursive: true, force: true });
      if (receipt) await saveJournal(join(vmPath(id), 'ReleaseRequests', receipt.requestId + '.json'), { ...receipt, state: 'aborted' });
    }
    throw error;
  }
}
