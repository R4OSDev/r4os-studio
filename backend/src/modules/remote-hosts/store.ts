import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { ProjectError } from '../projects/store.js';

export function remoteHostStore<T>(directory: string, request: { operation: string; id?: string; input?: unknown }): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/remote-hosts/cli.py', import.meta.url)), directory],
      { stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    let output = '', bytes = 0, settled = false;
    const finish = (error?: Error, result?: T) => { if (settled) return; settled = true; clearTimeout(timer); if (error) reject(error); else resolve(result!); };
    const timer = setTimeout(() => { child.kill('SIGKILL'); finish(new ProjectError('Remote Host storage timed out. Reconcile the original request.', 503)); }, 8000);
    child.on('error', () => finish(new ProjectError('Remote Host storage is unavailable.', 503)));
    child.stdin.on('error', () => { /* The original result is checked on close. */ });
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => { bytes += Buffer.byteLength(chunk); output += chunk; if (bytes > 8 * 1024**2) { child.kill('SIGKILL'); finish(new ProjectError('Remote Host response is too large.', 413)); } });
    child.on('close', () => {
      try { const value = JSON.parse(output); if (value.error) finish(new ProjectError(value.error, value.code)); else if (Object.hasOwn(value, 'result')) finish(undefined, value.result); else throw new Error(); }
      catch { finish(new ProjectError('Remote Host storage is unavailable. Reconcile the original request.', 503)); }
    });
    child.stdin.end(JSON.stringify(request));
  });
}
