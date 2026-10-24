import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { projectsDirectory } from '../projects/store.js';
import { validId, VmError } from '../virtual-machines/paths.js';

/** The child holds flock until the bounded server operation releases its pipe. */
export async function withVmLease<T>(id: string, work: (guard: () => void) => Promise<T>, purpose?: 'reset'): Promise<T> {
  if (!validId(id)) throw new VmError('Invalid virtual machine ID.', 400);
  const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/project-development/lease.py', import.meta.url)),
    'manual', projectsDirectory(), id, ...(purpose ? [purpose] : [])], { stdio: ['pipe', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
  child.stdin.on('error', () => {});
  let alive = true;
  child.on('close', () => { alive = false; });
  try {
    await new Promise<void>((resolve, reject) => {
      let output = '';
      const timer = setTimeout(() => { child.kill(); reject(new VmError('VM reservation did not respond.', 503)); }, 5000);
      const finish = (error?: Error) => { clearTimeout(timer); if (error) reject(error); else resolve(); };
      child.on('error', () => finish(new VmError('VM reservation support is unavailable.', 503)));
      child.on('close', () => finish(new VmError('VM reservation was not confirmed.', 503)));
      child.stdout.on('data', (part) => {
        output += part.toString();
        if (output.length > 8192) { child.kill(); finish(new VmError('Invalid VM reservation response.', 503)); return; }
        if (!output.includes('\n')) return;
        try { const value = JSON.parse(output.split('\n')[0]); finish(value.locked ? undefined : new VmError(value.error ?? 'VM reservation failed.', value.code ?? 503)); }
        catch { finish(new VmError('Invalid VM reservation response.', 503)); }
      });
    });
    if (!alive) throw new VmError('The VM reservation ended.', 503);
    const guard = () => { if (!alive) throw new VmError('The VM reservation ended before the operation completed.', 409); };
    return await work(guard);
  } finally {
    child.stdin.end();
    const cleanup = setTimeout(() => child.kill('SIGKILL'), 1000); cleanup.unref();
    child.once('close', () => clearTimeout(cleanup));
  }
}
