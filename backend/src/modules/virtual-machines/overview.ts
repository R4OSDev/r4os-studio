import { lstat, stat, readdir, readFile, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { root } from './paths.js';

/** Display-only invalidation facts. Execution still uses activeTool/images and
 * all original admission checks, independently of this short-lived read cache. */
export async function overviewFingerprint(): Promise<string | null> {
  const facts: unknown[] = [];
  async function file(path: string) {
    try {
      const info = await lstat(path, { bigint: true });
      facts.push([path, ...[info.dev, info.ino, info.mode, info.uid, info.size, info.mtimeNs, info.ctimeNs].map(String)]);
      if (info.isSymbolicLink()) {
        const target = await realpath(path), value = await stat(path, { bigint: true });
        facts.push([target, ...[value.dev, value.ino, value.mode, value.size, value.mtimeNs, value.ctimeNs].map(String)]);
      }
      return info;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      facts.push([path, null]);
    }
  }
  async function entries(path: string, maximum: number) {
    await file(path);
    try {
      const names = (await readdir(path)).sort();
      if (names.length > maximum) throw new Error('Display inventory is not cacheable.');
      return names;
    } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []; throw error; }
  }
  try {
    const profile = join(root, 'Profiles/versions.json'); await file(profile);
    let selected: { id?: string; external?: boolean } | undefined;
    try { selected = JSON.parse(await readFile(profile, 'utf8')).defaults?.qemu; } catch { /* Original readers report invalid profiles. */ }
    const local = selected && !selected.external && /^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,127}$/.test(selected.id ?? '')
      ? join(root, 'Toolchains/QEMU', selected.id!, 'bin') : '/usr/bin';
    for (const binary of ['qemu-system-x86_64', 'qemu-img']) await file(join(local, binary));
    await file('/usr/bin/systemctl');
    await file(process.env.STUDIO_VM_NETWORK_CAPABILITY ?? '/etc/r4os-studio-vms/network.json');
    for (const directory of ['/etc/systemd/system', '/run/systemd/system', '/usr/lib/systemd/system']) {
      await file(directory); await file(join(directory, 'r4os-studio-vm@.service'));
      for (const name of ['r4os-studio-vm@.service.d', 'service.d']) {
        const path = join(directory, name);
        for (const entry of await entries(path, 64)) await file(join(path, entry));
      }
    }
    const directory = join(root, 'Images');
    for (const entry of await entries(directory, 256)) {
      if (!/^[a-zA-Z0-9_.-]{1,100}$/.test(entry) || entry.startsWith('.')) continue;
      if (!(await file(join(directory, entry)))?.isDirectory()) continue;
      await file(join(directory, entry, 'image.json')); await file(join(directory, entry, 'disk.img'));
    }
    return JSON.stringify(facts);
  } catch { return null; }
}
