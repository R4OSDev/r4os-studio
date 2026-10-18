import { createConnection } from 'node:net';
import { join } from 'node:path';
import { runtimePath, VmError } from './paths.js';

/** One private QMP connection per request. Events never count as command replies. */
export function qmp(id: string, command: string, args?: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(join(runtimePath(id), 'qmp.sock'));
    let pending = ''; let finished = false;
    const timer = setTimeout(() => finish(new VmError('The virtual machine did not respond.')), 5000);
    function finish(error?: Error, value?: Record<string, unknown>) {
      if (finished) return; finished = true; clearTimeout(timer); socket.destroy();
      if (error) reject(error); else resolve(value ?? {});
    }
    socket.on('error', () => finish(new VmError('The virtual machine is not ready.')));
    socket.on('close', () => { if (!finished) finish(new VmError('The virtual machine disconnected.')); });
    socket.on('data', (chunk) => {
      pending += chunk.toString();
      if (pending.length > 2_000_000) { finish(new VmError('Invalid monitor response.')); return; }
      let newline: number;
      while ((newline = pending.indexOf('\n')) !== -1) {
        const line = pending.slice(0, newline).trim(); pending = pending.slice(newline + 1);
        if (!line) continue;
        try {
          const message = JSON.parse(line);
          if (message.QMP) socket.write(JSON.stringify({ execute: 'qmp_capabilities', id: 'cap' }) + '\n');
          else if (message.id === 'cap') {
            if (message.error) finish(new VmError('Monitor negotiation failed.'));
            else socket.write(JSON.stringify({ execute: command, ...(args ? { arguments: args } : {}), id: 'command' }) + '\n');
          } else if (message.id === 'command') {
            if (message.error) finish(new VmError(String(message.error.desc ?? 'Monitor command failed.')));
            else finish(undefined, message.return);
          }
        } catch { finish(new VmError('Invalid monitor response.')); }
      }
    });
  });
}
