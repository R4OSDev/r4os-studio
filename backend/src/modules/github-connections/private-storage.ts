import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, mkdir, open, rename, unlink } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { ProjectError } from '../projects/store.js';

export async function githubDirectory(directory: string) {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  if (!(await lstat(directory)).isDirectory()) throw new ProjectError('GitHub storage is unavailable.', 503);
}

export async function readGitHubJson<T>(path: string): Promise<T | null> {
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK).catch((error: NodeJS.ErrnoException) => {
    if (error.code === 'ENOENT') return null;
    throw error;
  });
  if (!file) return null;
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.nlink !== 1 || (stat.mode & 0o077) || stat.size > 4 * 1024 * 1024) {
      throw new ProjectError('GitHub storage is invalid.', 503);
    }
    return JSON.parse(await file.readFile('utf8')) as T;
  } finally { await file.close(); }
}

export async function saveGitHubJson(path: string, value: unknown) {
  const directory = dirname(path);
  const temporary = join(directory, `.github-${randomUUID()}.tmp`);
  const file = await open(temporary, 'wx', 0o600);
  try {
    try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); }
    finally { await file.close(); }
    await rename(temporary, path);
    const parent = await open(directory, constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW);
    try { await parent.sync(); } finally { await parent.close(); }
  } finally { await unlink(temporary).catch(() => {}); }
}

export async function withGitHubLock<T>(path: string, work: () => Promise<T>): Promise<T | undefined> {
  const file = await open(path, constants.O_CREAT | constants.O_RDWR | constants.O_NOFOLLOW | constants.O_NONBLOCK, 0o600);
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.nlink !== 1 || (stat.mode & 0o077)) throw new ProjectError('GitHub lock storage is invalid.', 503);
    // The child and parent share the open file description. Closing it in the
    // parent releases the kernel lock even when the server has been killed.
    const locked = await new Promise<boolean>((resolve, reject) => {
      const child = spawn('/usr/bin/flock', ['-n', '3'], { stdio: ['ignore', 'ignore', 'ignore', file.fd] });
      child.once('error', reject);
      child.once('exit', code => code === 0 || code === 1 ? resolve(code === 0) : reject(new Error('GitHub lock failed.')));
    });
    if (locked) return await work();
  } finally { await file.close(); }
}
