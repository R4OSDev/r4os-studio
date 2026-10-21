import { connect } from 'node:net';
import { existsSync } from 'node:fs';
import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { ProjectError } from '../projects/store.js';

export function agentHost<T>(request: Record<string, unknown>): Promise<T> {
  return new Promise((resolve, reject) => {
    const socket = connect(process.env.STUDIO_AGENTS_SOCKET ?? '/run/r4os-studio-agents/host.sock');
    socket.setEncoding('utf8');
    let pending = '', settled = false;
    const finish = (error?: Error, value?: T) => {
      if (settled) return;
      settled = true; clearTimeout(timer); socket.destroy();
      if (error) reject(error); else resolve(value!);
    };
    const timer = setTimeout(() => finish(new ProjectError('The agent coordinator did not respond.', 503)), 25_000);
    socket.on('error', () => finish(new ProjectError('Agent host support is unavailable.', 503)));
    socket.on('connect', () => socket.end(JSON.stringify(request) + '\n'));
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      if (pending.length > 2 * 1024 * 1024) return finish(new ProjectError('Agent response exceeds the limit.', 503));
      if (!pending.includes('\n')) return;
      try {
        const value = JSON.parse(pending.split('\n')[0]);
        if (value.error) finish(new ProjectError(value.error, value.code));
        else if (Object.hasOwn(value, 'result')) finish(undefined, value.result as T);
        else finish(new ProjectError('Invalid agent coordinator response.', 503));
      } catch { finish(new ProjectError('Invalid agent coordinator response.', 503)); }
    });
    socket.on('end', () => { if (!settled) finish(new ProjectError('Agent coordinator connection closed.', 503)); });
  });
}

export async function cancelProviderRuns(directory: string, providerId: string): Promise<void> {
  const socket = process.env.STUDIO_AGENTS_SOCKET ?? '/run/r4os-studio-agents/host.sock';
  if (existsSync(socket)) {
    await agentHost({ operation: 'cancel_provider', providerId }); return;
  }
  // If the coordinator is down, preserve credentials until existing run records
  // can be reconciled. Absence of host support alone does not break account setup.
  let entries: string[];
  try { entries = await readdir(join(directory, '.studio/agents')); } catch { return; }
  for (const id of entries) {
    if (!/^[a-f0-9-]{36}$/.test(id)) continue;
    try {
      const meta = JSON.parse(await readFile(join(directory, '.studio/agents', id, 'worker.json'), 'utf8'));
      if (meta.providerId === providerId) throw new ProjectError('Restore the agent coordinator before disconnecting a provider with run records.', 503);
    } catch (error) { if (error instanceof ProjectError) throw error; }
  }
}
