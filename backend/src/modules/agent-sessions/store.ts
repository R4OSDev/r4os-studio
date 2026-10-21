import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { componentRoot } from '../components/tools.js';
import { ProjectError } from '../projects/store.js';

export function providerDirectory() {
  return process.env.STUDIO_DATA_DIR ?? fileURLToPath(new URL('../../../../Data/LLMProvider/', import.meta.url));
}

export function sessionStore<T>(directory: string, request: Record<string, unknown>, providers = providerDirectory()): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/agent-sessions/session_store.py', import.meta.url)),
      directory, componentRoot(), providers], { stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', settled = false;
    const finish = (error?: Error, value?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      if (error) reject(error); else resolve(value!);
    };
    const timer = setTimeout(() => { child.kill('SIGKILL'); finish(new ProjectError('Session storage did not respond.')); }, 15_000);
    child.on('error', () => finish(new ProjectError('Session storage is unavailable.')));
    child.stdin.on('error', () => {});
    child.stdout.on('data', (chunk) => {
      output += chunk.toString();
      if (output.length > 2 * 1024 * 1024) { child.kill('SIGKILL'); finish(new ProjectError('Session response is too large.')); }
    });
    child.on('close', () => {
      try {
        const result = JSON.parse(output);
        if (result.error) finish(new ProjectError(result.error, result.code));
        else if (Object.hasOwn(result, 'result')) finish(undefined, result.result as T);
        else finish(new ProjectError('Invalid session response.'));
      } catch { finish(new ProjectError('Session storage is unavailable.')); }
    });
    child.stdin.end(JSON.stringify(request));
  });
}
