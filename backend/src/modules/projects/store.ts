import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { ProjectSummary } from '../../../../shared/projects.js';
import { componentRoot } from '../components/tools.js';

// Releases share the persistent data root already configured for R4OS components.
export function projectsDirectory() {
  return process.env.STUDIO_R4OS_DIR
    ? join(process.env.STUDIO_R4OS_DIR, '..', 'Projects')
    : fileURLToPath(new URL('../../../../Data/Projects/', import.meta.url));
}

export class ProjectError extends Error {
  constructor(message: string, public statusCode = 503) { super(message); }
}

export function projectStore<T>(directory: string, request: Record<string, unknown>, helper: 'store' | 'sdk' | 'create' | 'system_prompt' | 'skill_prompt' | 'delete' | 'project_agents' | 'project_pins' | 'clear_cache' | 'editor' = 'store', signal?: AbortSignal): Promise<T> {
  if (signal && (helper !== 'editor' || request.operation !== 'search'))
    return Promise.reject(new ProjectError('Only Workspace searches support cancellation.', 400));
  if (signal?.aborted) return Promise.reject(new ProjectError('Search cancelled.', 499));
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL(`../../../../scripts/projects/${helper}.py`, import.meta.url)), directory, componentRoot()],
      { detached: true, stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', settled = false, cancelled = false;
    const terminate = () => {
      try { if (child.pid) process.kill(-child.pid, 'SIGKILL'); }
      catch { child.kill('SIGKILL'); }
    };
    const finish = (error?: Error, result?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer); signal?.removeEventListener('abort', abort);
      if (error) reject(error); else resolve(result!);
    };
    const abort = () => { if (!settled) { cancelled = true; if (child.exitCode === null && child.signalCode === null) terminate(); } };
    const timer = setTimeout(() => { terminate(); if (!cancelled) finish(new ProjectError('Project service did not respond.')); }, ['store', 'system_prompt', 'skill_prompt', 'project_agents', 'editor'].includes(helper) ? 10_000 : 180_000);
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
    child.on('error', () => { if (!cancelled) finish(new ProjectError('Project storage is unavailable.')); });
    child.stdin.on('error', () => { /* Process exit is handled below. */ });
    child.stdout.on('data', (chunk) => {
      output += chunk.toString();
      if (output.length > 2 * 1024 * 1024) { terminate(); finish(new ProjectError('Project inventory is too large.')); }
    });
    child.on('close', () => {
      // A cancelled read keeps its process owner until this original close.
      if (cancelled) { finish(new ProjectError('Search cancelled.', 499)); return; }
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
