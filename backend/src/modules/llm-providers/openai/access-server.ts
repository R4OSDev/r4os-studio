import { createServer } from 'node:net';
import type { Server, Socket } from 'node:net';
import { chmod, lstat, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { ProviderError } from '../errors.js';
import type { ProviderManager } from '../service.js';
import type { NativeBinding } from './credentials.js';

/** Host-only credential bridge. It cannot execute model, thread or tool RPCs. */
export class NativeAccessServer {
  private server?: Server;
  private clients = new Set<Socket>();
  private inode?: number;
  private path: string;
  constructor(directory: string, private manager: ProviderManager) { this.path = join(directory, '.a.sock'); }

  async start() {
    // Never unlink a live peer. An orphaned socket is removed only after a
    // failed connection, with unchanged inode and the same private owner.
    try {
      const stat = await lstat(this.path);
      if (!stat.isSocket() || stat.uid !== process.getuid?.() || (stat.mode & 0o777) !== 0o600) throw new Error('Private OpenAI access socket is unavailable.');
      const { connect } = await import('node:net');
      await new Promise<void>((resolve, reject) => {
        const socket = connect(this.path); socket.setTimeout(1000);
        socket.once('connect', () => { socket.destroy(); reject(new Error('The original OpenAI access service is still active.')); });
        socket.once('timeout', () => { socket.destroy(); reject(new Error('The original OpenAI access service could not be confirmed.')); });
        socket.once('error', error => {
          socket.destroy();
          if ('code' in error && error.code === 'ECONNREFUSED') resolve(); else reject(error);
        });
      });
      if ((await lstat(this.path)).ino !== stat.ino) throw new Error('Private OpenAI access socket changed.');
      await unlink(this.path);
    } catch (error) { if (!(error instanceof Error && 'code' in error && error.code === 'ENOENT')) throw error; }
    this.server = createServer(socket => {
      this.clients.add(socket); socket.once('close', () => this.clients.delete(socket));
      socket.on('error', () => {}); socket.setTimeout(55_000, () => socket.destroy());
      let raw = Buffer.alloc(0), submitted = false;
      socket.on('data', chunk => {
        if (submitted) return;
        raw = Buffer.concat([raw, chunk]);
        if (raw.length > 4096) { socket.destroy(); return; }
        if (!raw.includes(10)) return;
        submitted = true;
        void (async () => {
          try {
            const value = JSON.parse(raw.toString('utf8')) as { action?: string; id?: unknown; binding?: NativeBinding };
            if (Object.keys(value).some(key => !['action', 'id', 'binding'].includes(key)) || typeof value.id !== 'string'
              || !['snapshot', 'credential', 'limits'].includes(value.action ?? '') || ['credential', 'limits'].includes(value.action ?? '') && !value.binding) throw new ProviderError('Invalid private account request.');
            const result = value.action === 'limits' ? await this.manager.nativeLimits(value.id, value.binding!) : await this.manager.nativeAccess(value.id, value.binding, value.action === 'credential');
            socket.end(JSON.stringify({ result }) + '\n');
          } catch (error) {
            socket.end(JSON.stringify({ error: error instanceof ProviderError ? error.message : 'The private OpenAI account access is unavailable.', code: error instanceof ProviderError ? error.statusCode : 503 }) + '\n');
          }
        })();
      });
    });
    await new Promise<void>((resolve, reject) => {
      this.server!.once('error', reject);
      this.server!.listen(this.path, () => resolve());
    });
    await chmod(this.path, 0o600); this.inode = (await lstat(this.path)).ino;
  }

  async close() {
    for (const socket of this.clients) socket.destroy();
    if (this.server) await new Promise<void>(resolve => this.server!.close(() => resolve()));
    try { if ((await lstat(this.path)).ino === this.inode) await unlink(this.path); }
    catch (error) { if (!(error instanceof Error && 'code' in error && error.code === 'ENOENT')) throw error; }
  }
}
