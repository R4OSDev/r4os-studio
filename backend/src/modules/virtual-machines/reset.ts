import { createReadStream } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { lstat, mkdir, open, readFile, readdir, realpath, rename, rm, link } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { VmConfig, VmResetInput } from '../../../../shared/virtual-machines.js';
import { root, vmPath, validId, VmError } from './paths.js';
import { createShareImage } from './share.js';
import { exec } from './systemd.js';

interface Receipt extends VmResetInput { schema: 1; nextRevision: string; state: 'preparing' | 'aborted' | 'complete' }
interface Journal { schema: 1; vmId: string; requestId: string; previousRevision: string; nextRevision: string }
const instances = join(root, 'Instances');
const journalPath = (id: string) => join(instances, `.reset-${id}.json`);
const receiptPath = (id: string, request: string) => join(vmPath(id), 'ResetRequests', request + '.json');
async function sync(path: string) { const file = await open(path, 'r'); try { await file.sync(); } finally { await file.close(); } }
async function directory(path: string) {
  if ((await realpath(path)) !== resolve(path) || !(await lstat(path)).isDirectory()) throw new VmError('Invalid VM reset directory.');
}
async function read<T>(path: string): Promise<T | undefined> {
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink() || info.size > 16384 || await realpath(path) !== resolve(path)) throw new VmError('Invalid VM reset receipt.');
    return JSON.parse(await readFile(path, 'utf8')) as T;
  } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined; throw error; }
}
async function save(path: string, value: unknown) {
  const temp = path + '.' + randomUUID() + '.tmp'; const file = await open(temp, 'wx', 0o600);
  try {
    try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); } finally { await file.close(); }
    await rename(temp, path); await sync(dirname(path));
  } finally { await rm(temp, { force: true }); }
}
function matches(receipt: Receipt, input: VmResetInput) {
  return receipt.schema === 1 && validId(receipt.nextRevision) && receipt.kind === input.kind
    && receipt.requestId === input.requestId && receipt.expectedRevision === input.expectedRevision && receipt.confirm === true;
}
export async function recoverReset(id: string) {
  const journal = await read<Journal>(journalPath(id)); if (!journal) return;
  if (journal.schema !== 1 || journal.vmId !== id || !validId(journal.requestId) || !validId(journal.nextRevision)) throw new VmError('Invalid VM reset journal.');
  const config = await read<VmConfig>(join(vmPath(id), 'vm.json'));
  const receipt = await read<Receipt>(receiptPath(id, journal.requestId));
  if (!config || !receipt || receipt.schema !== 1 || receipt.requestId !== journal.requestId || !['system', 'exchange'].includes(receipt.kind)
    || receipt.nextRevision !== journal.nextRevision || receipt.expectedRevision !== journal.previousRevision
    || ![journal.previousRevision, journal.nextRevision].includes(config.revision ?? config.imageSha256)) throw new VmError('The VM reset journal needs maintenance. Existing data was preserved.');
  // Before publication this is prepared data; after publication it is the old
  // disk/Exchange. Never remove or exchange the current VM directory here.
  await rm(join(instances, `.release-${id}-${journal.requestId}`), { recursive: true, force: true });
  await sync(instances);
  await save(receiptPath(id, journal.requestId), { ...receipt, state: config.revision === journal.nextRevision ? 'complete' : 'aborted' });
  await rm(journalPath(id)); await sync(instances);
}
export async function completedReset(id: string, input: VmResetInput) {
  const value = await read<Receipt>(receiptPath(id, input.requestId));
  if (value && !matches(value, input)) throw new VmError('This reset request ID belongs to another operation.');
  return value?.state === 'complete';
}
async function clone(source: string, target: string, kind: VmResetInput['kind'], relative = '') {
  await mkdir(target, { mode: 0o700 });
  for (const entry of await readdir(source)) {
    const name = relative ? relative + '/' + entry : entry;
    if (name === 'vm.json' || (kind === 'system' && name === 'Disks/disk.qcow2')
      || (kind === 'exchange' && (name === 'Exchange' || name === 'Disks/exchange.img' || name.startsWith('Disks/.exchange-')))) continue;
    const from = join(source, entry), to = join(target, entry), info = await lstat(from);
    if (info.isSymbolicLink()) throw new VmError('Linked VM data requires manual maintenance before reset.');
    if (info.isDirectory()) await clone(from, to, kind, name);
    else if (info.isFile()) await link(from, to);
    else throw new VmError('Special VM files require manual maintenance before reset.');
  }
  await sync(target);
}
export async function resetDisks(id: string, config: VmConfig, input: VmResetInput, imageBinary: string, stopped: () => Promise<void>, leaseGuard: () => void) {
  if (!validId(id) || !validId(input.requestId) || !['system', 'exchange'].includes(input.kind) || input.confirm !== true) throw new VmError('Invalid VM reset request.', 400);
  await directory(vmPath(id)); await directory(join(vmPath(id), 'Disks'));
  try { await directory(join(vmPath(id), 'Exchange')); } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const receipts = join(vmPath(id), 'ResetRequests'); await mkdir(receipts, { mode: 0o700, recursive: true }); await directory(receipts);
  const previous = await read<Receipt>(receiptPath(id, input.requestId));
  if (previous && !matches(previous, input)) throw new VmError('This reset request ID belongs to another operation.');
  if (previous?.state === 'complete') return;
  if ((config.revision ?? config.imageSha256) !== input.expectedRevision) throw new VmError('The VM changed after confirmation. Review and confirm its current state.');
  const receipt: Receipt = { ...input, schema: 1, nextRevision: previous?.nextRevision ?? randomUUID(), state: 'preparing' };
  await save(receiptPath(id, input.requestId), receipt);
  const stage = join(instances, `.release-${id}-${input.requestId}`); let journaled = false;
  try {
    await rm(stage, { recursive: true, force: true });
    if (input.kind === 'system') {
      if (!/^[a-zA-Z0-9_.-]{1,100}$/.test(config.imageId)) throw new VmError('Invalid bound VM image.');
      const base = join(root, 'Images', config.imageId, 'disk.img');
      if (await realpath(base) !== resolve(base) || !(await lstat(base)).isFile()) throw new VmError('Invalid VM base image.');
      const hash = createHash('sha256'); for await (const chunk of createReadStream(base)) hash.update(chunk);
      if (hash.digest('hex') !== config.imageSha256) throw new VmError('The bound image checksum changed.');
    }
    await clone(vmPath(id), stage, input.kind);
    if (input.kind === 'system') {
      await exec(imageBinary, ['create', '-f', 'qcow2', '-F', 'raw', '-b', join(root, 'Images', config.imageId, 'disk.img'), join(stage, 'Disks/disk.qcow2')], { timeout: 30_000 });
      await sync(join(stage, 'Disks/disk.qcow2'));
    } else {
      await mkdir(join(stage, 'Exchange/Share'), { recursive: true, mode: 0o700 });
      await sync(join(stage, 'Exchange/Share'));
      await createShareImage(stage);
      await save(join(stage, 'Exchange/state.json'), { schema: 1, baseline: {}, pending: false, session: randomUUID(), lastSyncedAt: new Date().toISOString() });
    }
    await save(join(stage, 'vm.json'), { ...config, revision: receipt.nextRevision,
      ...(input.kind === 'system' ? { systemGeneration: receipt.nextRevision } : {}) });
    await sync(join(stage, 'Disks')); await sync(stage);
    await stopped();
    await save(journalPath(id), { schema: 1, vmId: id, requestId: input.requestId, previousRevision: input.expectedRevision, nextRevision: receipt.nextRevision });
    journaled = true;
    leaseGuard();
    await exec('/usr/bin/python3', [fileURLToPath(new URL('../../../../scripts/vm-release-swap.py', import.meta.url)), instances, id, input.requestId], { timeout: 30_000 });
    await sync(instances); await recoverReset(id);
  } catch (error) {
    if (journaled) { await recoverReset(id); if (await completedReset(id, input)) return; }
    else { await rm(stage, { recursive: true, force: true }); await save(receiptPath(id, input.requestId), { ...receipt, state: 'aborted' }); }
    throw error;
  }
}
