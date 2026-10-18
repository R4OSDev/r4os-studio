import { lstat, readdir, mkdir, open, rm, rename } from 'node:fs/promises';
import { join } from 'node:path';
import { exec } from './systemd.js';
import { VmError } from './paths.js';

export const validFilename = (name: string) => /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}$/.test(name) && !/[.]$/.test(name);
export async function shareFiles(directory: string) {
  const files: { name: string; size: number }[] = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (!entry.isFile() || !validFilename(entry.name)) throw new VmError('The exchange folder accepts plain files with ASCII names only.');
    const info = await lstat(join(directory, entry.name));
    files.push({ name: entry.name, size: info.size });
  }
  if (new Set(files.map((file) => file.name.toLowerCase())).size !== files.length) throw new VmError('Exchange filenames must be unique ignoring case.');
  if (files.length > 128 || files.reduce((sum, f) => sum + f.size, 0) > 96 * 1024 * 1024) throw new VmError('The exchange folder is limited to 128 files and 96 MiB.');
  return files.sort((a, b) => a.name.localeCompare(b.name));
}

/** A real FAT32 image: QEMU's native vvfat FAT32 layout is not reliable. */
export async function createShareImage(directory: string) {
  const share = join(directory, 'Exchange/Share');
  const files = await shareFiles(share);
  const staging = join(directory, 'Disks/.exchange-new.img');
  await mkdir(join(directory, 'Disks'), { recursive: true });
  await rm(staging, { force: true });
  const file = await open(staging, 'wx', 0o600);
  await file.truncate(257 * 1024 * 1024);
  const mbr = Buffer.alloc(512); mbr[450] = 0x0c;
  mbr.writeUInt32LE(2048, 454); mbr.writeUInt32LE(256 * 1024 * 1024 / 512, 458);
  mbr[510] = 0x55; mbr[511] = 0xaa; await file.write(mbr, 0, 512, 0); await file.close();
  try {
    await exec('/usr/sbin/mkfs.fat', ['-F', '32', '-n', 'R4SHARE', '--offset=2048', staging], { timeout: 30_000 });
    for (const entry of files) await exec('/usr/bin/mcopy', ['-i', staging + '@@1048576', join(share, entry.name), '::/'], { timeout: 30_000 });
    const ready = await open(staging, 'r');
    try { await ready.sync(); } finally { await ready.close(); }
    await rename(staging, join(directory, 'Disks/exchange.img'));
    const parent = await open(join(directory, 'Disks'), 'r');
    try { await parent.sync(); } finally { await parent.close(); }
  } catch (error) { await rm(staging, { force: true }); throw error; }
}
