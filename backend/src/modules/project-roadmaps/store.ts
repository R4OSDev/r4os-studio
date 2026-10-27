import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import type { ProjectRoadmapState } from '../../../../shared/project-roadmaps.js';
import { ProjectError } from '../projects/store.js';

export function roadmapStore(directory: string, request: { operation: 'read' | 'initialize'; projectId: string }): Promise<ProjectRoadmapState> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/project-roadmaps/cli.py', import.meta.url)), directory],
      { detached: true, stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', settled = false;
    const finish = (error?: Error, result?: ProjectRoadmapState) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(result!);
    };
    const terminate = () => {
      try { if (child.pid) process.kill(-child.pid, 'SIGKILL'); } catch { child.kill('SIGKILL'); }
    };
    const timer = setTimeout(() => { terminate(); finish(new ProjectError('The roadmap service did not respond.')); }, 10_000);
    child.on('error', () => finish(new ProjectError('Roadmap storage is unavailable.')));
    child.stdin.on('error', () => { /* The close event handles rejected input. */ });
    child.stdout.on('data', (chunk: Buffer) => {
      output += chunk.toString();
      if (Buffer.byteLength(output) > 2 * 1024 * 1024) {
        terminate(); finish(new ProjectError('The roadmap response is too large.', 413));
      }
    });
    child.on('close', () => {
      try {
        const value = JSON.parse(output);
        if (value.error) finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value.result);
        else finish(new ProjectError('Roadmap storage returned an invalid response.'));
      } catch { finish(new ProjectError('Roadmap storage is unavailable.')); }
    });
    child.stdin.end(JSON.stringify(request));
  });
}
