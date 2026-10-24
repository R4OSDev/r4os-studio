import { constants } from 'node:fs';
import { lstat, readdir, mkdir, open, rm, rename, realpath } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { exec } from './systemd.js';
import { VmError } from './paths.js';

export const exchangeLimits = { files: 128, bytes: 96 * 1024 * 1024, directories: 128, depth: 6, seconds: 120 };
export interface ShareEntry { name: string; size: number; kind: 'file' | 'directory' }
export const validFilename = (name: string) => /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(name) && !/[.]$/.test(name);
export function validSharePath(name: string, directory = false) {
  const parts = name.split('/');
  return parts.length <= exchangeLimits.depth && parts.every(validFilename) && (parts.length === 1 && !directory || parts[0].toLowerCase() === 'build');
}
export function boundShare(entries: ShareEntry[]) {
  const files = entries.filter((e) => e.kind === 'file');
  if (files.length > exchangeLimits.files || files.reduce((sum, f) => sum + f.size, 0) > exchangeLimits.bytes
    || entries.length - files.length > exchangeLimits.directories) throw new VmError('Exchange is limited to 128 files, 96 MiB and 128 folders (depth 6), including Build and reserved files.');
  const names = new Map(entries.map((e) => [e.name.toLowerCase(), e]));
  if (names.size !== entries.length) throw new VmError('Exchange paths must be unique ignoring case.');
  for (const entry of entries) {
    if (!validSharePath(entry.name, entry.kind === 'directory') || !Number.isSafeInteger(entry.size) || entry.size < 0) throw new VmError('Unsupported Exchange path or entry.');
    const parts = entry.name.split('/'); parts.pop();
    if (parts.length && names.get(parts.join('/').toLowerCase())?.kind !== 'directory') throw new VmError('An Exchange parent changed between file and folder. Preserve the image and resolve the host/guest conflict.');
  }
}
export async function shareFiles(directory: string): Promise<ShareEntry[]> {
  if ((await realpath(directory)) !== resolve(directory)) throw new VmError('Linked Exchange folders are not supported.');
  const result: ShareEntry[] = [], deadline = Date.now() + exchangeLimits.seconds * 1000;
  async function scan(path = '') {
    if (Date.now() > deadline) throw new VmError('Exchange scan exceeded its deadline.');
    const base = join(directory, path), info = await lstat(base);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new VmError('Exchange links and special files are not supported.');
    const children = await readdir(base, { withFileTypes: true });
    if (children.length > exchangeLimits.files + exchangeLimits.directories) throw new VmError('Too many Exchange entries.');
    for (const child of children) {
      const name = path ? path + '/' + child.name : child.name, stat = await lstat(join(directory, name));
      const kind = stat.isDirectory() ? 'directory' : 'file';
      if ((!stat.isDirectory() && !stat.isFile()) || stat.isSymbolicLink() || stat.isFile() && stat.nlink !== 1 || !validSharePath(name, kind === 'directory'))
        throw new VmError('Exchange accepts plain ASCII files and the Build folder only; links and special files are rejected.');
      result.push({ name, size: kind === 'directory' ? 0 : stat.size, kind });
      // Validate the complete entry graph after scanning; quotas apply while scanning too.
      if (result.length > exchangeLimits.files + exchangeLimits.directories || result.reduce((sum, e) => sum + e.size, 0) > exchangeLimits.bytes) throw new VmError('Exchange quota exceeded.');
      if (kind === 'directory') await scan(name);
    }
  }
  await scan(); boundShare(result);
  return result.sort((a, b) => a.name.localeCompare(b.name));
}
export async function readShareFile(directory: string, entry: ShareEntry) {
  const path = join(directory, entry.name);
  if (await realpath(path) !== resolve(path)) throw new VmError('Linked Exchange paths are not supported.');
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size !== entry.size || stat.size > exchangeLimits.bytes) throw new VmError('Exchange file changed during synchronization.');
    const data = Buffer.alloc(entry.size + 1); let offset = 0;
    while (offset < data.length) { const part = await file.read(data, offset, data.length - offset, null); if (!part.bytesRead) break; offset += part.bytesRead; }
    if (offset !== entry.size) throw new VmError('Exchange file changed during synchronization.');
    return data.subarray(0, offset);
  } finally { await file.close(); }
}
/** A real offline FAT32 image. Never use this on an image attached to QEMU. */
export async function createShareImage(directory: string) {
  const share = join(directory, 'Exchange/Share'), entries = await shareFiles(share);
  const staging = join(directory, 'Disks/.exchange-new.img'), deadline = Date.now() + exchangeLimits.seconds * 1000;
  const run = (command: string, args: string[]) => {
    const timeout = Math.min(30_000, deadline - Date.now());
    if (timeout <= 0) throw new VmError('Exchange import exceeded its deadline.');
    return exec(command, args, { timeout });
  };
  await mkdir(join(directory, 'Disks'), { recursive: true }); await rm(staging, { force: true });
  const file = await open(staging, 'wx', 0o600);
  try {
    await file.truncate(257 * 1024 * 1024);
    const mbr = Buffer.alloc(512); mbr[450] = 0x0c;
    mbr.writeUInt32LE(2048, 454); mbr.writeUInt32LE(256 * 1024 * 1024 / 512, 458);
    mbr[510] = 0x55; mbr[511] = 0xaa; await file.write(mbr, 0, 512, 0);
  } finally { await file.close(); }
  try {
    await run('/usr/sbin/mkfs.fat', ['-F', '32', '-n', 'R4SHARE', '--offset=2048', staging]);
    for (const entry of entries.filter((e) => e.kind === 'directory').sort((a, b) => a.name.split('/').length - b.name.split('/').length))
      await run('/usr/bin/mmd', ['-i', staging + '@@1048576', '::/' + entry.name]);
    for (const entry of entries.filter((e) => e.kind === 'file')) {
      await readShareFile(share, entry); // Recheck links/size immediately before mtools reads it.
      await run('/usr/bin/mcopy', ['-i', staging + '@@1048576', join(share, entry.name), '::/' + entry.name]);
    }
    const ready = await open(staging, 'r'); try { await ready.sync(); } finally { await ready.close(); }
    await rename(staging, join(directory, 'Disks/exchange.img'));
    const parent = await open(join(directory, 'Disks'), 'r'); try { await parent.sync(); } finally { await parent.close(); }
  } catch (error) { await rm(staging, { force: true }); throw error; }
}
