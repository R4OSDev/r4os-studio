import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ProjectSummary } from '../../../../shared/projects.js';

// Releases share the persistent data root already configured for R4OS components.
export function projectsDirectory() {
  return process.env.STUDIO_R4OS_DIR
    ? join(process.env.STUDIO_R4OS_DIR, '..', 'Projects')
    : fileURLToPath(new URL('../../../../Data/Projects/', import.meta.url));
}

export class ProjectError extends Error {
  constructor(message: string, public statusCode = 503) { super(message); }
}

export function projectStore<T>(directory: string, request: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/projects/store.py', import.meta.url)), directory],
      { stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', settled = false;
    const finish = (error?: Error, result?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(result!);
    };
    const timer = setTimeout(() => { child.kill('SIGKILL'); finish(new ProjectError('Project storage did not respond.')); }, 10_000);
    child.on('error', () => finish(new ProjectError('Project storage is unavailable.')));
    child.stdin.on('error', () => { /* Process exit is handled below. */ });
    child.stdout.on('data', (chunk) => {
      output += chunk.toString();
      if (output.length > 2 * 1024 * 1024) { child.kill('SIGKILL'); finish(new ProjectError('Project inventory is too large.')); }
    });
    child.on('close', () => {
      try {
        const value = JSON.parse(output);
        if (value.error) finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value.result as T);
        else finish(new ProjectError('Project storage returned an invalid response.'));
      } catch { finish(new ProjectError('Project storage is unavailable.')); }
    });
    child.stdin.end(JSON.stringify(request));
  });
}

export async function listProjects(directory: string): Promise<ProjectSummary[]> {
  const projects = await projectStore<ProjectSummary[]>(directory, { operation: 'list' });
  return projects.sort((left, right) => left.name.localeCompare(right.name, 'en', { numeric: true }));
}
