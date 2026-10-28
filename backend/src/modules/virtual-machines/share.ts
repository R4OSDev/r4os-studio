import { constants } from 'node:fs';
import { lstat, readdir, mkdir, mkdtemp, open, rm, rename, realpath } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { exec } from './systemd.js';
import { VmError } from './paths.js';
import { exchangeLimits, exchangePolicy, exchangeImageBytes } from './exchange-policy.js';

export { exchangeLimits } from './exchange-policy.js';
export interface ShareEntry { name: string; size: number; kind: 'file' | 'directory' }
export const validFilename = (name: string) => /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(name) && !/[.]$/.test(name);
export function validSharePath(name: string, directory = false) {
  const parts = name.split('/');
  return parts.length <= exchangeLimits.depth && parts.every(validFilename) && (parts.length === 1 && !directory || parts[0].toLowerCase() === 'build');
}
export function boundShare(entries: ShareEntry[]) {
  const files = entries.filter((e) => e.kind === 'file');
  if (files.length > exchangeLimits.files || files.reduce((sum, f) => sum + f.size, 0) > exchangeLimits.bytes
    || entries.length - files.length > exchangeLimits.directories) throw new VmError(`Exchange is limited to ${exchangeLimits.files} files, ${exchangeLimits.bytes / 1024 ** 3} GiB and ${exchangeLimits.directories} folders (depth ${exchangeLimits.depth}), including Build and reserved files.`);
  const names = new Map(entries.map((e) => [e.name.toLowerCase(), e]));
  if (names.size !== entries.length) throw new VmError('Exchange paths must be unique ignoring case.');
  for (const entry of entries) {
    if (entry.name.split('/').length > exchangeLimits.depth) throw new VmError(`Exchange path "${entry.name}" exceeds ${exchangeLimits.depth} levels. Existing files were preserved.`);
    if (!validSharePath(entry.name, entry.kind === 'directory') || !Number.isSafeInteger(entry.size) || entry.size < 0) throw new VmError('Unsupported Exchange path or entry.');
    const parts = entry.name.split('/'); parts.pop();
    if (parts.length && names.get(parts.join('/').toLowerCase())?.kind !== 'directory') throw new VmError('An Exchange parent changed between file and folder. Preserve the image and resolve the host/guest conflict.');
  }
}
export async function shareFiles(directory: string, deadline = Date.now() + exchangeLimits.seconds * 1000): Promise<ShareEntry[]> {
  if ((await realpath(directory)) !== resolve(directory)) throw new VmError('Linked Exchange folders are not supported.');
  const result: ShareEntry[] = []; let totalBytes = 0;
  async function scan(path = '') {
    if (Date.now() > deadline) throw new VmError('Exchange scan exceeded its deadline.');
    const base = join(directory, path), info = await lstat(base);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new VmError('Exchange links and special files are not supported.');
    const children = await readdir(base, { withFileTypes: true });
    if (children.length > exchangeLimits.files + exchangeLimits.directories) throw new VmError('Too many Exchange entries.');
    for (const child of children) {
      const name = path ? path + '/' + child.name : child.name, stat = await lstat(join(directory, name));
      const kind = stat.isDirectory() ? 'directory' : 'file';
      if (name.split('/').length > exchangeLimits.depth) throw new VmError(`Exchange path "${name}" exceeds ${exchangeLimits.depth} levels. Existing files were preserved.`);
      if ((!stat.isDirectory() && !stat.isFile()) || stat.isSymbolicLink() || stat.isFile() && stat.nlink !== 1 || !validSharePath(name, kind === 'directory'))
        throw new VmError('Exchange accepts plain ASCII files and the Build folder only; links and special files are rejected.');
      result.push({ name, size: kind === 'directory' ? 0 : stat.size, kind });
      totalBytes += kind === 'directory' ? 0 : stat.size;
      // Validate the complete entry graph after scanning; quotas apply while scanning too.
      if (result.length > exchangeLimits.files + exchangeLimits.directories || totalBytes > exchangeLimits.bytes) throw new VmError('Exchange quota exceeded.');
      if (kind === 'directory') await scan(name);
    }
  }
  await scan(); boundShare(result);
  return result.sort((a, b) => a.name.localeCompare(b.name));
}
/** Hash/copy in fixed chunks, including files up to the full payload quota. */
export async function hashShareFile(directory: string, entry: ShareEntry, deadline: number, target?: string) {
  const path = join(directory, entry.name);
  if (await realpath(path) !== resolve(path)) throw new VmError('Linked Exchange paths are not supported.');
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  let output: Awaited<ReturnType<typeof open>> | undefined;
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size !== entry.size || stat.size > exchangeLimits.bytes) throw new VmError('Exchange file changed during synchronization.');
    if (target) output = await open(target, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600);
    const data = Buffer.alloc(1024 * 1024), hash = createHash('sha256'); let offset = 0;
    while (true) {
      if (Date.now() > deadline) throw new VmError('Exchange synchronization exceeded its deadline.');
      const { bytesRead } = await file.read(data, 0, Math.min(data.length, entry.size - offset + 1), null);
      if (!bytesRead) break;
      offset += bytesRead;
      if (offset > entry.size) throw new VmError('Exchange file changed during synchronization.');
      const chunk = data.subarray(0, bytesRead); hash.update(chunk);
      if (output) await output.writeFile(chunk);
    }
    if (offset !== entry.size) throw new VmError('Exchange file changed during synchronization.');
    const after = await file.stat();
    if (after.size !== stat.size || after.mtimeMs !== stat.mtimeMs || after.ctimeMs !== stat.ctimeMs || after.nlink !== 1)
      throw new VmError('Exchange file changed during synchronization.');
    if (output) await output.sync();
    return hash.digest('hex');
  } finally { await output?.close(); await file.close(); }
}
/** A real offline FAT32 image. Never use this on an image attached to QEMU. */
export async function createShareImage(directory: string) {
  const share = join(directory, 'Exchange/Share'), entries = await shareFiles(share);
  const staging = join(directory, 'Disks/.exchange-new.img'), deadline = Date.now() + exchangeLimits.seconds * 1000;
  const run = (command: string, args: string[]) => {
    const timeout = deadline - Date.now();
    if (timeout <= 0) throw new VmError('Exchange import exceeded its deadline.');
    return exec(command, args, { timeout });
  };
  await mkdir(join(directory, 'Disks'), { recursive: true }); await rm(staging, { force: true });
  const file = await open(staging, 'wx', 0o600);
  try {
    await file.truncate(exchangeImageBytes);
    const mbr = Buffer.alloc(512); mbr[450] = 0x0c;
    mbr.writeUInt32LE(exchangePolicy.image.offsetBytes / 512, 454); mbr.writeUInt32LE(exchangePolicy.image.partitionBytes / 512, 458);
    mbr[510] = 0x55; mbr[511] = 0xaa; await file.write(mbr, 0, 512, 0);
  } finally { await file.close(); }
  const source = await mkdtemp(join(directory, 'Disks/.exchange-source-')), hashes = new Map<string, string>();
  try {
    await run('/usr/sbin/mkfs.fat', ['-F', '32', '-n', 'R4SHARE', '--offset=' + exchangePolicy.image.offsetBytes / 512, staging]);
    for (const entry of entries.filter((e) => e.kind === 'directory').sort((a, b) => a.name.split('/').length - b.name.split('/').length))
      await run('/usr/bin/mmd', ['-i', staging + '@@1048576', '::/' + entry.name]);
    for (const entry of entries.filter((e) => e.kind === 'file')) {
      // mtools reads a private, checked snapshot, never a changing host path.
      const payload = join(source, 'payload');
      hashes.set(entry.name, await hashShareFile(share, entry, deadline, payload));
      await run('/usr/bin/mcopy', ['-i', staging + '@@1048576', payload, '::/' + entry.name]);
      await rm(payload);
    }
    if (JSON.stringify(entries) !== JSON.stringify(await shareFiles(share, deadline))) throw new VmError('Host Exchange changed during import. Stop editing and retry.');
    for (const entry of entries.filter((e) => e.kind === 'file'))
      if (await hashShareFile(share, entry, deadline) !== hashes.get(entry.name)) throw new VmError('Host Exchange changed during import. Stop editing and retry.');
    const ready = await open(staging, 'r'); try { await ready.sync(); } finally { await ready.close(); }
    await rename(staging, join(directory, 'Disks/exchange.img'));
    const parent = await open(join(directory, 'Disks'), 'r'); try { await parent.sync(); } finally { await parent.close(); }
  } catch (error) { await rm(staging, { force: true }); throw error; }
  finally { await rm(source, { recursive: true, force: true }); }
}
