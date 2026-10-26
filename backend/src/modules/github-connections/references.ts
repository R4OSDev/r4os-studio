import { constants } from 'node:fs';
import { open, lstat, realpath } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { listProjects, ProjectError } from '../projects/store.js';
import type { GitHubProjectBinding, GitHubProjectReference } from '../../../../shared/project-github.js';

export async function projectBinding(directory: string, id: string): Promise<GitHubProjectBinding | null> {
  if (!/^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(id)) throw new ProjectError('Invalid project identity.', 400);
  const root = resolve(directory), parts = [root, join(root, id), join(root, id, '.studio'), join(root, id, '.studio/git')];
  for (const part of parts) {
    const stat = await lstat(part).catch((e: NodeJS.ErrnoException) => { if (e.code === 'ENOENT') return null; throw e; });
    if (!stat) return null;
    if (!stat.isDirectory() || await realpath(part) !== part) throw new ProjectError('Git project storage needs host maintenance.', 503);
  }
  const file = await open(join(parts[3], 'binding.json'), constants.O_RDONLY | constants.O_NOFOLLOW).catch((e: NodeJS.ErrnoException) => { if (e.code === 'ENOENT') return null; throw e; });
  if (!file) return null;
  try {
    const stat = await file.stat();
    if (!stat.isFile() || stat.nlink !== 1 || stat.size > 16384) throw new ProjectError('Git project binding is invalid.', 503);
    const value = JSON.parse(await file.readFile('utf8')) as GitHubProjectBinding;
    if (value.schema !== 1 || !Number.isSafeInteger(value.revision) || value.revision < 1
      || typeof value.connectionId !== 'string' || !/^[a-f0-9-]{36}$/.test(value.connectionId)
      || !Number.isSafeInteger(value.userId) || !Number.isSafeInteger(value.repository?.id)
      || typeof value.branch !== 'string') throw new ProjectError('Git project binding is invalid.', 503);
    return value;
  } finally { await file.close(); }
}
export async function connectionProjects(directory: string, connectionId: string): Promise<GitHubProjectReference[]> {
  const projects = await listProjects(directory);
  if (projects.length > 5000) throw new ProjectError('Project reference listing exceeded its limit.', 503);
  const result: GitHubProjectReference[] = [];
  for (const project of projects) {
    if ((await projectBinding(directory, project.id))?.connectionId === connectionId) result.push({ id: project.id, name: project.name });
  }
  return result;
}
