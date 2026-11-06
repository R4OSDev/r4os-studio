import { lstat, mkdir, open, readFile, realpath, rename, rm } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { VmError } from './paths.js';

export async function syncDirectory(path: string) {
  const file = await open(path, 'r'); try { await file.sync(); } finally { await file.close(); }
}
export async function privateDirectory(path: string) {
  await mkdir(path, { recursive: true, mode: 0o700 });
  if (await realpath(path) !== resolve(path) || !(await lstat(path)).isDirectory()) throw new VmError('Invalid VM journal directory.');
}
export async function readJournal<T>(path: string, limit = 256 * 1024): Promise<T | undefined> {
  try {
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink() || info.size > limit || await realpath(path) !== resolve(path)) throw new VmError('Invalid VM journal.');
    return JSON.parse(await readFile(path, 'utf8')) as T;
  } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return; throw error; }
}
export async function saveJournal(path: string, value: unknown) {
  const temporary = path + '.' + randomUUID() + '.tmp', file = await open(temporary, 'wx', 0o600);
  try {
    try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); } finally { await file.close(); }
    await rename(temporary, path); await syncDirectory(dirname(path));
  } finally { await rm(temporary, { force: true }); }
}
