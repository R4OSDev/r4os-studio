import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { ProjectError } from '../projects/store.js';

/** No compiler, shell, credentials or model process is needed to manage skills. */
export function skillStore<T>(directory: string, request: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/skills/store.py', import.meta.url)), directory, process.execPath],
      { detached: true, stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', settled = false;
    const kill = () => { try { if (child.pid) process.kill(-child.pid, 'SIGKILL'); } catch { child.kill('SIGKILL'); } };
    const finish = (error?: Error, result?: T) => {
      if (settled) return; settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(result!);
    };
    const timer = setTimeout(() => { kill(); finish(new ProjectError('Skill storage did not respond.', 503)); }, 15_000);
    child.on('error', () => finish(new ProjectError('Skill storage is unavailable.', 503)));
    child.stdin.on('error', () => {});
    child.stdout.on('data', (chunk) => {
      output += chunk.toString();
      if (output.length > 2 * 1024 * 1024) { kill(); finish(new ProjectError('Skill response exceeds its limit.', 503)); }
    });
    child.on('close', () => {
      try {
        const value = JSON.parse(output);
        if (typeof value.error === 'string') finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value.result as T);
        else finish(new ProjectError('Skill storage returned an invalid response.', 503));
      } catch { finish(new ProjectError('Skill storage is unavailable. Existing data was preserved.', 503)); }
    });
    child.stdin.end(JSON.stringify(request));
  });
}
