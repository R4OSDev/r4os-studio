import { createConnection } from 'node:net';
import { version } from '../../version.js';
import type { UpdateStatus } from '../../../../shared/updates.js';

export class UpdateError extends Error { constructor(message: string, public statusCode = 503) { super(message); } }
export function updateCommand(command: string, release?: { tag: string; commit: string }): Promise<UpdateStatus> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(process.env.STUDIO_UPDATE_SOCKET ?? '/run/r4os-studio-updates/control.sock');
    let text = '';
    socket.setTimeout(5_000);
    socket.on('connect', () => socket.write(JSON.stringify({ command, ...(release ? { release } : {}) }) + '\n'));
    socket.on('data', (chunk) => {
      text += chunk.toString();
      if (text.length > 128 * 1024) { socket.destroy(); reject(new UpdateError('The update service returned an invalid response.')); return; }
      if (!text.includes('\n')) return;
      socket.end();
      try {
        const response = JSON.parse(text.split('\n')[0]) as { status?: UpdateStatus; error?: string; code?: number };
        if (response.error) reject(new UpdateError(response.error, response.code ?? 409));
        else if (response.status) resolve(response.status);
        else reject(new UpdateError('The update service returned an invalid response.'));
      } catch { reject(new UpdateError('The update service returned an invalid response.')); }
    });
    socket.on('timeout', () => socket.destroy(new Error('Timeout')));
    socket.on('error', () => reject(new UpdateError('The host update service is unavailable. Install the update host support first.')));
    socket.on('end', () => { if (!text.includes('\n')) reject(new UpdateError('The update service disconnected.')); });
  });
}
export function unavailableStatus(): UpdateStatus {
  return { enabled: false, installed: { version, commit: null }, latest: null, available: false,
    source: 'Not configured', phase: 'unavailable', message: 'The host update service is unavailable.', error: null,
    lastChecked: null, nextCheck: null, checkIntervalSeconds: 21600, history: [] };
}
