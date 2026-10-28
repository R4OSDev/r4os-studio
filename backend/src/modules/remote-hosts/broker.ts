import { connect } from 'node:net';
import { ProjectError } from '../projects/store.js';

/** Private fixed protocol for the unprivileged SSH/SFTP broker.
 * Public requests select saved IDs/revisions, never SSH options or credentials.
 * No connection is opened by catalog management.
 */
export interface RemoteTargetBinding {
  hostId: string; endpointRevision: number; credentialRevision: number; trustRevision: number;
}
export type RemoteBrokerRequest = { protocol: 1; operation: 'capabilities' }
  | { protocol: 1; operation: 'test'; hostId: string; input: unknown }
  | { protocol: 1; operation: 'read'; hostId: string; requestId: string };
type RemoteLifecycleRequest = { protocol: 1; operation: 'jobs'; hostId: string }
  | { protocol: 1; operation: 'job'; hostId: string; projectId: string; jobId: string }
  | { protocol: 1; operation: 'review_job'; hostId: string; projectId: string; jobId: string; input: unknown }
  | { protocol: 1; operation: 'review_receipt'; hostId: string; projectId: string; jobId: string; requestId: string };
export interface RemoteBrokerCapabilities { protocol: 1; test: boolean; commands: boolean; files: boolean }

export function remoteHostBroker<T>(request: RemoteBrokerRequest | RemoteLifecycleRequest): Promise<T> {
  return new Promise((resolve, reject) => {
    const socket = connect(process.env.STUDIO_REMOTE_HOSTS_SOCKET ?? '/run/r4os-studio-remote/host.sock');
    socket.setEncoding('utf8'); let raw = '', bytes = 0, settled = false;
    const finish = (error?: Error, value?: T) => { if (settled) return; settled = true; clearTimeout(timer); socket.destroy(); if (error) reject(error); else resolve(value!); };
    const timer = setTimeout(() => finish(new ProjectError('Remote host support did not respond. Preserve the original request ID.', 503)), 10_000);
    socket.on('error', () => finish(new ProjectError('Remote host support is unavailable.', 503)));
    socket.on('connect', () => socket.end(JSON.stringify(request) + '\n'));
    socket.on('data', (chunk: string) => {
      bytes += Buffer.byteLength(chunk); raw += chunk;
      if (bytes > 131072) { finish(new ProjectError('The remote broker response exceeded its limit.', 503)); return; }
      if (!raw.includes('\n')) return;
      try { const value = JSON.parse(raw.split('\n')[0]); if (value.error) finish(new ProjectError(value.error, value.code)); else if (Object.hasOwn(value, 'result')) finish(undefined, value.result); else throw new Error(); }
      catch { finish(new ProjectError('Remote host support returned an invalid receipt.', 503)); }
    });
    socket.on('end', () => finish(new ProjectError('The remote broker connection closed. Inspect the original request.', 503)));
  });
}
