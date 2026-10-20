import { access, readFile, realpath, stat } from 'node:fs/promises';
import { createReadStream, constants } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';

type ToolKind = 'qemu' | 'codex';
interface ToolRecord {
  id: string; version: string; binary: string; imageBinary?: string; external?: boolean;
  sha256?: string; binarySha256?: string; imageBinarySha256?: string;
}
const checked = new Map<string, string>();
const fallback = { qemu: '/usr/bin/qemu-system-x86_64', codex: '/opt/r4os-studio/bin/codex' };
export function componentRoot() {
  return process.env.STUDIO_R4OS_DIR ?? fileURLToPath(new URL('../../../../Data/R4OS/', import.meta.url));
}
export async function activeTool(kind: ToolKind): Promise<ToolRecord> {
  let profile: { defaults: Partial<Record<ToolKind, ToolRecord>> };
  try { profile = JSON.parse(await readFile(join(componentRoot(), 'Profiles/versions.json'), 'utf8')); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { id: 'system', version: '', binary: fallback[kind], ...(kind === 'qemu' ? { imageBinary: '/usr/bin/qemu-img' } : {}) }; throw error; }
  const tool = profile.defaults[kind];
  if (!tool) return { id: 'system', version: '', binary: fallback[kind], ...(kind === 'qemu' ? { imageBinary: '/usr/bin/qemu-img' } : {}) };
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.+-]{0,127}$/.test(tool.id)) throw new Error('Invalid active tool identity.');
  const expected = tool.external ? fallback[kind] : join(componentRoot(), 'Toolchains', kind === 'qemu' ? 'QEMU' : 'Codex', tool.id, kind === 'qemu' ? 'bin/qemu-system-x86_64' : 'codex');
  if (resolve(tool.binary) !== resolve(expected)) throw new Error('Invalid active tool path.');
  async function verify(path: string, hash?: string) {
    if (!hash || !/^[a-f0-9]{64}$/.test(hash)) throw new Error('Active tool checksum is missing.');
    const canonical = await realpath(path), info = await stat(path);
    if (canonical !== resolve(path) || !info.isFile()) throw new Error('Invalid active tool file.');
    await access(path, constants.X_OK);
    const signature = `${info.size}:${info.mtimeMs}:${info.ctimeMs}:${hash}`;
    if (checked.get(path) === signature) return;
    const digest = createHash('sha256');
    for await (const chunk of createReadStream(path)) digest.update(chunk);
    if (digest.digest('hex') !== hash) throw new Error('The active tool checksum changed. Select a verified installation.');
    checked.set(path, signature);
  }
  await verify(tool.binary, tool.binarySha256 ?? (tool.external ? tool.sha256 : undefined));
  if (kind === 'qemu') {
    const imagePath = tool.external ? '/usr/bin/qemu-img' : join(componentRoot(), 'Toolchains/QEMU', tool.id, 'bin/qemu-img');
    if (tool.imageBinary !== imagePath) throw new Error('Invalid active QEMU image tool path.');
    if (!tool.external) await verify(imagePath, tool.imageBinarySha256);
  }
  return tool;
}
