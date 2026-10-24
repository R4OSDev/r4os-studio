import { constants } from 'node:fs';
import { open, lstat, rename, readFile, readdir } from 'node:fs/promises';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { basename, join } from 'node:path';
import { runtimePath, validId, VmError } from './paths.js';

export const exchangeMarker = 'STXCHG.JSN';
export const reservedExchangeName = (name: string) => name.toUpperCase() === exchangeMarker;
interface Identity { schema: 1; vmId: string; generation: string; nonce: string; published: boolean }
const bytes = (value: Identity) => Buffer.from(JSON.stringify({ interface: 'r4os-studio-exchange', schema: 1,
  vmId: value.vmId, generation: value.generation, nonce: value.nonce }) + '\n');
async function durable(path: string, data: string | Buffer) {
  const file = await open(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
  try { await file.writeFile(data); await file.sync(); } finally { await file.close(); }
}
async function sync(directory: string) { const file = await open(directory, 'r'); try { await file.sync(); } finally { await file.close(); } }
async function plain(path: string) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || info.size > 4096) throw new VmError('Invalid Exchange identity file. Preserve the exchange data.');
  return readFile(path);
}
async function identity(directory: string): Promise<Identity | undefined> {
  let data: Buffer;
  try { data = await plain(join(directory, 'Exchange/identity.json')); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
  const value = JSON.parse(data.toString()) as Identity;
  if (value.schema !== 1 || value.vmId !== basename(directory) || !validId(value.vmId) || !validId(value.generation)
    || !/^[a-f0-9]{64}$/.test(value.nonce) || typeof value.published !== 'boolean') throw new VmError('Unsupported Exchange identity. Preserve the exchange data.');
  return value;
}
/** Called under the VM lease, after old guest changes were exported and while QEMU is stopped. */
export async function prepareExchangeIdentity(directory: string) {
  let value = await identity(directory);
  const marker = join(directory, 'Exchange/Share', exchangeMarker), metadata = join(directory, 'Exchange/identity.json');
  if (!value) {
    if ((await readdir(join(directory, 'Exchange/Share'))).some(reservedExchangeName))
      throw new VmError('STXCHG.JSN is reserved. Move the existing file before starting the VM.');
    if (!validId(basename(directory))) throw new VmError('Invalid Exchange VM identity.');
    value = { schema: 1, vmId: basename(directory), generation: randomUUID(), nonce: randomBytes(32).toString('hex'), published: false };
    await durable(metadata, JSON.stringify(value) + '\n'); await sync(join(directory, 'Exchange'));
  }
  let current: Buffer | undefined;
  try { current = await plain(marker); }
  catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  if (current && !current.equals(bytes(value))) throw new VmError('The reserved Exchange marker changed. Preserve the image and restore its identity.');
  if (!current) {
    if (value.published) throw new VmError('The reserved Exchange marker is missing. Preserve the image and restore its identity.');
    await durable(marker, bytes(value)); await sync(join(directory, 'Exchange/Share'));
  }
  if (!value.published) {
    const temp = metadata + '.' + randomUUID();
    await durable(temp, JSON.stringify({ ...value, published: true }) + '\n'); await rename(temp, metadata); await sync(join(directory, 'Exchange'));
  }
}
/** Read-only: never creates or repairs identities while a guest is running. */
export async function exchangeIdentity(directory: string) {
  const value = await identity(directory);
  if (!value?.published) return null;
  const expected = bytes(value);
  return { schema: 1, vmId: value.vmId, generation: value.generation, marker: exchangeMarker,
    markerBase64: expected.toString('base64'), markerSha256: createHash('sha256').update(expected).digest('hex') };
}
export async function verifyExchangeMarker(directory: string, share: string) {
  const value = await exchangeIdentity(directory);
  if (value && !(await plain(join(share, exchangeMarker))).equals(Buffer.from(value.markerBase64, 'base64')))
    throw new VmError('The guest Exchange marker changed. The image has been preserved.');
}
/** The immutable release pinned at VM start also owns ExecStopPost. Never substitute the current web release. */
export async function exchangeWorkerCapability(id: string) {
  try {
    const pin = JSON.parse(await readFile(join(runtimePath(id), 'worker.json'), 'utf8'));
    if (typeof pin.release !== 'string' || !/^\/opt\/r4os-studio\/releases\/[a-zA-Z0-9.-]+$/.test(pin.release)) return { buildTreeVersion: 0 };
    const value = JSON.parse(await readFile(join(pin.release, 'shared/exchange-host.json'), 'utf8'));
    return { buildTreeVersion: value.interface === 'r4os-studio-exchange' && value.schema === 1 && value.buildTreeVersion === 1 ? 1 : 0 };
  } catch { return { buildTreeVersion: 0 }; }
}
