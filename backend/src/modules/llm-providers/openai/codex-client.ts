import { spawn } from 'node:child_process';
import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import { createInterface } from 'node:readline';
import { version } from '../../../version.js';

export interface AuthClient {
  request<T = unknown>(method: string, params?: unknown): Promise<T>;
  close(): Promise<void>;
}

export type AuthNotification = (method: string, params: Record<string, unknown>) => void;
export type AuthClientFactory = (home: string, notify: AuthNotification, exited: () => void) => AuthClient;

const unavailable = 'OpenAI sign-in is unavailable. Please try again.';

/** Only account RPC is exposed by the Studio adapter; no agent turns or tools run. */
export class CodexClient implements AuthClient {
  private child: ChildProcessWithoutNullStreams;
  private sequence = 0;
  private pending = new Map<number, { resolve: (value: unknown) => void; reject: (error: Error) => void; timer: NodeJS.Timeout }>();
  private ready: Promise<void>;
  private stopped = false;
  private closing = false;

  constructor(binary: string, home: string, notify: AuthNotification, exited: () => void) {
    const env = { ...process.env, CODEX_HOME: home };
    for (const key of ['OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN', 'CODEX_AUTH_JSON', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE']) {
      delete (env as Record<string, string | undefined>)[key];
    }
    this.child = spawn(binary, ['app-server', '--listen', 'stdio://', '-c', 'cli_auth_credentials_store="file"'], {
      cwd: home, env, stdio: ['pipe', 'pipe', 'pipe'],
    });
    // Never forward upstream stderr, account responses or tokens to HTTP logs.
    this.child.stderr.resume();
    const lines = createInterface({ input: this.child.stdout });
    const stop = () => {
      if (this.stopped) return;
      this.stopped = true;
      for (const request of this.pending.values()) {
        clearTimeout(request.timer);
        request.reject(new Error(unavailable));
      }
      this.pending.clear();
      if (!this.closing) exited();
    };
    this.child.on('error', stop);
    this.child.on('exit', stop);
    this.child.stdin.on('error', stop);
    lines.on('line', (line) => {
      if (line.length > 1_048_576) { this.child.kill(); return; }
      let message: Record<string, unknown>;
      try { message = JSON.parse(line) as Record<string, unknown>; } catch { return; }
      if (!message || typeof message !== 'object' || Array.isArray(message)) return;
      if ('id' in message && !('method' in message)) {
        const request = this.pending.get(Number(message.id));
        if (!request) return;
        clearTimeout(request.timer);
        this.pending.delete(Number(message.id));
        if (message.error) {
          const raw = typeof message.error === 'object' && message.error !== null && 'message' in message.error
            ? String(message.error.message) : '';
          const hint = /device.*not enabled|enable.*device/i.test(raw)
            ? 'Enable device-code sign-in in your ChatGPT settings, then try again.' : unavailable;
          request.reject(new Error(hint));
        } else request.resolve(message.result);
      } else if (typeof message.method === 'string' && 'id' in message) {
        this.child.stdin.write(JSON.stringify({ id: message.id, error: { code: -32601, message: 'Not supported' } }) + '\n');
      } else if (typeof message.method === 'string') {
        notify(message.method, (message.params ?? {}) as Record<string, unknown>);
      }
    });
    this.ready = this.send('initialize', {
      clientInfo: { name: 'r4os_studio', title: 'R4OS Studio', version },
      capabilities: { experimentalApi: false },
    }).then(() => {
      this.child.stdin.write(JSON.stringify({ method: 'initialized' }) + '\n');
    });
    // The first request still receives initialization errors, without an unhandled rejection.
    void this.ready.catch(() => {});
  }

  private send(method: string, params?: unknown): Promise<unknown> {
    if (this.stopped || this.closing) return Promise.reject(new Error(unavailable));
    return new Promise((resolve, reject) => {
      const id = ++this.sequence;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('OpenAI sign-in timed out. Please try again.'));
      }, 45_000);
      timer.unref();
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(JSON.stringify({ id, method, ...(params === undefined ? {} : { params }) }) + '\n', (error) => {
        if (error && this.pending.delete(id)) { clearTimeout(timer); reject(new Error(unavailable)); }
      });
    });
  }

  async request<T>(method: string, params?: unknown): Promise<T> {
    await this.ready;
    return await this.send(method, params) as T;
  }

  async close(): Promise<void> {
    if (this.stopped) return;
    this.closing = true;
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => { this.child.kill('SIGKILL'); resolve(); }, 2000);
      timer.unref();
      this.child.once('exit', () => { clearTimeout(timer); resolve(); });
      this.child.once('error', () => { clearTimeout(timer); resolve(); });
      this.child.kill('SIGTERM');
    });
  }
}
