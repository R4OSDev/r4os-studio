import { access, rm } from 'node:fs/promises';
import { constants } from 'node:fs';
import { randomUUID } from 'node:crypto';
import type { Provider, ProviderLogin, ProviderUsage, ResetRequest, ResetResult } from '../../../../shared/llm-providers.js';
import { CodexClient } from './openai/codex-client.js';
import type { AuthClient, AuthClientFactory } from './openai/codex-client.js';
import { ProviderStore, validProviderId } from './store.js';
import type { ProviderRecord } from './store.js';
import { ProviderError } from './errors.js';
import { readUsage, redeemReset } from './openai/usage.js';

type Login = ProviderLogin & { owner: string; id?: string; timer?: NodeJS.Timeout };
type Runtime = { client: AuthClient; login?: Login; unavailable: boolean; retired?: boolean };
type AccountResult = { account: { type: string; email?: string | null; planType?: string | null } | null };

export interface ProviderOptions {
  directory: string;
  binary: string;
  binaryResolver?: () => Promise<string>;
  clientFactory?: AuthClientFactory;
  loginTimeoutMs?: number;
  beforeDisconnect?: (id: string) => Promise<void>;
}

export class ProviderManager {
  private store: ProviderStore;
  private runtimes = new Map<string, Runtime>();
  private locks = new Map<string, Promise<unknown>>();
  private usages = new Map<string, ProviderUsage>();
  private loginTimeout: number;

  constructor(private options: ProviderOptions) {
    this.store = new ProviderStore(options.directory);
    this.loginTimeout = options.loginTimeoutMs ?? 15 * 60_000;
  }

  async available(): Promise<boolean> {
    if (this.options.clientFactory) return true;
    try { await access(await this.options.binaryResolver?.() ?? this.options.binary, constants.X_OK); return true; } catch { return false; }
  }

  private exclusive<T>(id: string, action: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(id) ?? Promise.resolve();
    const next = previous.catch(() => {}).then(action);
    this.locks.set(id, next);
    void next.finally(() => { if (this.locks.get(id) === next) this.locks.delete(id); }).catch(() => {});
    return next;
  }

  private async record(id: string): Promise<ProviderRecord> {
    if (!validProviderId(id)) throw new ProviderError('Provider not found.', 404);
    const record = (await this.store.list()).find((item) => item.id === id);
    if (!record) throw new ProviderError('Provider not found.', 404);
    return record;
  }

  private present(record: ProviderRecord): Provider {
    const runtime = this.runtimes.get(record.id);
    return { id: record.id, name: record.name, type: 'openai', createdAt: record.createdAt,
      account: record.account ? { email: record.account.email, plan: record.account.plan } : null,
      status: runtime?.unavailable ? 'unavailable'
        : runtime?.login?.status === 'pending' ? 'signing_in' : record.connected ? 'connected' : 'disconnected' };
  }

  async list(): Promise<Provider[]> { return (await this.store.list()).map((record) => this.present(record)); }

  private async runtime(id: string): Promise<Runtime> {
    const existing = this.runtimes.get(id);
    if (existing && !existing.unavailable && !existing.retired) return existing;
    if (existing) { await existing.client.close(); this.runtimes.delete(id); }
    const home = await this.store.home(id);
    const binary = this.options.clientFactory ? this.options.binary : await this.options.binaryResolver?.() ?? this.options.binary;
    const factory: AuthClientFactory = this.options.clientFactory ?? ((home, notify, exited) => new CodexClient(binary, home, notify, exited));
    const runtime = {} as Runtime;
    runtime.unavailable = false;
    runtime.client = factory(home, (method, params) => {
      if (method === 'account/rateLimits/updated' || method === 'account/updated') {
        this.usages.delete(id);
        return;
      }
      if (method !== 'account/login/completed') return;
      void this.exclusive(id, async () => {
        if (this.runtimes.get(id) !== runtime || runtime.login?.status !== 'pending' || runtime.login.id !== params.loginId) return;
        if (params.success === true) {
          try {
            const provider = await this.syncAccount(id, runtime);
            if (provider.status !== 'connected') throw new Error();
            this.finish(runtime.login, 'connected');
          } catch {
            this.finish(runtime.login, 'failed', 'Sign-in could not be verified. Please try again.');
            await this.retire(id, runtime);
          }
        } else {
          this.finish(runtime.login, 'failed', 'OpenAI sign-in was not completed. Please try again.');
          await this.retire(id, runtime);
        }
      }).catch(() => {});
    }, () => {
      this.usages.delete(id);
      runtime.unavailable = true;
      if (runtime.login?.status === 'pending') this.finish(runtime.login, 'failed', 'The sign-in service stopped. Please try again.');
    });
    this.runtimes.set(id, runtime);
    return runtime;
  }

  private finish(login: Login, status: ProviderLogin['status'], message?: string) {
    clearTimeout(login.timer);
    login.status = status;
    login.message = message;
    delete login.userCode;
    delete login.verificationUrl;
  }

  private async retire(id: string, runtime: Runtime) {
    this.usages.delete(id);
    runtime.retired = true;
    await runtime.client.close();
    await rm(await this.store.home(id), { recursive: true, force: true });
  }

  private async syncAccount(id: string, runtime: Runtime): Promise<Provider> {
    const result = await runtime.client.request<AccountResult>('account/read', { refreshToken: false });
    const account = result.account?.type === 'chatgpt' ? result.account : null;
    await this.store.change((records) => {
      const record = records.find((item) => item.id === id);
      if (!record) return;
      record.connected = account !== null;
      record.account = account ? { email: typeof account.email === 'string' ? account.email : null,
        plan: typeof account.planType === 'string' ? account.planType : null } : null;
    });
    const provider = this.present(await this.record(id));
    // A completion notification is being handled while the attempt is still pending.
    if (account) provider.status = 'connected';
    return provider;
  }

  async get(id: string): Promise<Provider> {
    return this.exclusive(id, async () => {
      const record = await this.record(id);
      const current = this.runtimes.get(id);
      if (current?.login?.status === 'pending') return this.present(record);
      try { return await this.syncAccount(id, await this.runtime(id)); }
      catch { return { ...this.present(record), status: 'unavailable' }; }
    });
  }

  async create(name: string): Promise<Provider> {
    const clean = name.trim();
    if (!clean || clean.length > 80 || [...clean].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) {
      throw new ProviderError('Enter a provider name between 1 and 80 characters.');
    }
    const record: ProviderRecord = { id: randomUUID(), name: clean, type: 'openai', connected: false,
      account: null, createdAt: new Date().toISOString() };
    await this.store.change((records) => {
      if (records.length >= 20) throw new ProviderError('Remove an existing provider before adding another.', 409);
      records.push(record);
    });
    return this.present(record);
  }

  private async connectedRuntime(id: string): Promise<Runtime> {
    const record = await this.record(id);
    if (!record.connected || this.runtimes.get(id)?.login?.status === 'pending') {
      throw new ProviderError('Connect this OpenAI subscription before reading usage or using a reset.', 409);
    }
    return this.runtime(id);
  }

  private async readUsageLocked(id: string, runtime: Runtime): Promise<ProviderUsage> {
    const usage = await readUsage(runtime.client);
    this.usages.set(id, usage);
    return usage;
  }

  async usage(id: string, refresh = false): Promise<ProviderUsage> {
    return this.exclusive(id, async () => {
      const runtime = await this.connectedRuntime(id);
      const cached = this.usages.get(id);
      if (!refresh && cached && Date.now() - Date.parse(cached.fetchedAt) < 15_000) return cached;
      try { return await this.readUsageLocked(id, runtime); }
      catch { throw new ProviderError('OpenAI usage could not be loaded. Please try again.', 502); }
    });
  }

  async consumeReset(id: string, request: ResetRequest): Promise<ResetResult> {
    return this.exclusive(id, async () => {
      const runtime = await this.connectedRuntime(id);
      let outcome: ResetResult['outcome'];
      try { outcome = await redeemReset(runtime.client, request); }
      catch { throw new ProviderError('The reset result could not be confirmed. Retry the same attempt to avoid using another reset.', 502); }
      finally { this.usages.delete(id); }
      // A confirmed redemption stays successful even if the subsequent read fails.
      // Never infer new quotas or re-consume a credit to recover a usage-read error.
      let usage: ProviderUsage | null = null;
      try { usage = await this.readUsageLocked(id, runtime); } catch { /* The UI can retry this read separately. */ }
      return { outcome, usage };
    });
  }

  async start(id: string, owner: string): Promise<ProviderLogin> {
    return this.exclusive(id, async () => {
      const record = await this.record(id);
      if (record.connected) throw new ProviderError('Disconnect this provider before signing in again.', 409);
      if (this.runtimes.get(id)?.login?.status === 'pending') throw new ProviderError('A sign-in is already in progress for this provider.', 409);
      // A new attempt never inherits credentials from a failed/cancelled attempt.
      await this.disconnectLocked(id);
      const runtime = await this.runtime(id);
      const login: Login = { status: 'pending', owner, expiresAt: new Date(Date.now() + this.loginTimeout).toISOString() };
      runtime.login = login;
      try {
        const response = await runtime.client.request<{ type: string; loginId: string; verificationUrl: string; userCode: string }>(
          'account/login/start', { type: 'chatgptDeviceCode' });
        if (response.type !== 'chatgptDeviceCode' || typeof response.loginId !== 'string'
          || response.verificationUrl !== 'https://auth.openai.com/codex/device'
          || typeof response.userCode !== 'string' || !/^[A-Za-z0-9-]{4,64}$/.test(response.userCode)) {
          throw new Error();
        }
        login.id = response.loginId;
        login.verificationUrl = response.verificationUrl;
        login.userCode = response.userCode;
        login.timer = setTimeout(() => {
          void this.exclusive(id, async () => {
            if (runtime.login !== login || login.status !== 'pending') return;
            this.finish(login, 'expired', 'This code has expired. Start a new sign-in.');
            try { await runtime.client.request('account/login/cancel', { loginId: login.id }); } catch { /* No credentials are exposed on failure. */ }
            await this.retire(id, runtime);
          }).catch(() => {});
        }, Math.max(1, Date.parse(login.expiresAt) - Date.now()));
        login.timer.unref();
      } catch (error) {
        const message = error instanceof Error && error.message.startsWith('Enable device-code')
          ? error.message : 'OpenAI sign-in could not be started. Please try again.';
        this.finish(login, 'failed', message);
        // Also cancel a malformed or timed-out upstream attempt.
        await this.retire(id, runtime);
        this.runtimes.delete(id);
        return this.publicLogin(login);
      }
      return this.publicLogin(login);
    });
  }

  private publicLogin(login: Login): ProviderLogin {
    return { status: login.status, expiresAt: login.expiresAt,
      ...(login.message ? { message: login.message } : {}),
      ...(login.status === 'pending' ? { verificationUrl: login.verificationUrl, userCode: login.userCode } : {}) };
  }

  async login(id: string, owner: string): Promise<ProviderLogin | null> {
    await this.record(id);
    const login = this.runtimes.get(id)?.login;
    if (!login) return null;
    if (login.owner !== owner) throw new ProviderError('This sign-in belongs to another browser session.', 403);
    return this.publicLogin(login);
  }

  async cancel(id: string, owner: string): Promise<void> {
    return this.exclusive(id, async () => {
      await this.record(id);
      const runtime = this.runtimes.get(id);
      if (!runtime?.login) return;
      if (runtime.login.owner !== owner) throw new ProviderError('This sign-in belongs to another browser session.', 403);
      if (runtime.login.status !== 'pending') return;
      this.finish(runtime.login, 'cancelled');
      try { await runtime.client.request('account/login/cancel', { loginId: runtime.login.id }); }
      finally { await this.retire(id, runtime); this.runtimes.delete(id); }
    });
  }

  private async disconnectLocked(id: string): Promise<Provider> {
    await this.record(id);
    await this.options.beforeDisconnect?.(id);
    this.usages.delete(id);
    const runtime = this.runtimes.get(id);
    if (runtime?.login) this.finish(runtime.login, 'cancelled');
    if (runtime) { await runtime.client.close(); this.runtimes.delete(id); }
    // No shared CLI session is used. Removing this home disconnects only this provider locally.
    await rm(await this.store.home(id), { recursive: true, force: true });
    await this.store.change((records) => {
      const record = records.find((item) => item.id === id);
      if (record) { record.connected = false; record.account = null; }
    });
    return this.present(await this.record(id));
  }

  async disconnect(id: string): Promise<Provider> {
    return this.exclusive(id, () => this.disconnectLocked(id));
  }

  async remove(id: string): Promise<void> {
    await this.exclusive(id, async () => {
      await this.disconnectLocked(id);
      await this.store.change((records) => {
        const index = records.findIndex((item) => item.id === id);
        if (index !== -1) records.splice(index, 1);
      });
    });
  }

  async close(): Promise<void> {
    for (const runtime of this.runtimes.values()) clearTimeout(runtime.login?.timer);
    await Promise.all([...this.runtimes.values()].map((runtime) => runtime.client.close()));
    this.runtimes.clear();
    this.usages.clear();
  }
}

