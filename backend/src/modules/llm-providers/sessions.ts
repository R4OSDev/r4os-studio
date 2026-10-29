import { randomBytes, timingSafeEqual } from 'node:crypto';
import { hostname, networkInterfaces } from 'node:os';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { ProviderError } from './errors.js';

/** Browser ownership and same-origin protection for provider administration. */
export class ProviderSessions {
  private sessions = new Map<string, { token: string; expires: number }>();
  private allowedHosts = new Set(['localhost', '127.0.0.1', '::1', '[::1]', hostname(),
    ...Object.values(networkInterfaces()).flatMap((items) => (items ?? []).map((item) => item.address)),
    ...(process.env.STUDIO_ALLOWED_HOSTS ?? '').split(',').map((host) => host.trim()).filter(Boolean)]);

  validateRequest(request: FastifyRequest, reply: FastifyReply) {
    reply.header('Cache-Control', 'no-store');
    if (!this.allowedHosts.has(request.hostname)) throw new ProviderError('This host is not allowed to access provider settings.', 403);
    if (request.headers['sec-fetch-site'] === 'cross-site') throw new ProviderError('Cross-origin provider requests are not allowed.', 403);
    if (request.headers.origin) {
      let origin: URL;
      try { origin = new URL(request.headers.origin); } catch { throw new ProviderError('Invalid request origin.', 403); }
      if (origin.origin !== new URL(`${request.protocol}://${request.headers.host}`).origin) throw new ProviderError('Cross-origin provider requests are not allowed.', 403);
    }
  }

  get(request: FastifyRequest, reply: FastifyReply, create = false) {
    const id = request.headers.cookie?.split(';').map((part) => part.trim()).find((part) => part.startsWith('studio_provider_session='))?.split('=')[1];
    const existing = id && this.sessions.get(id);
    if (existing && existing.expires > Date.now()) return { id, ...existing };
    if (!create) throw new ProviderError('Reload provider settings before continuing.', 403);
    for (const [key, value] of this.sessions) if (value.expires < Date.now()) this.sessions.delete(key);
    if (this.sessions.size >= 256) this.sessions.delete(this.sessions.keys().next().value!);
    const nextId = randomBytes(32).toString('hex');
    const next = { token: randomBytes(32).toString('hex'), expires: Date.now() + 24 * 60 * 60_000 };
    this.sessions.set(nextId, next);
    reply.header('Set-Cookie', `studio_provider_session=${nextId}; Path=/api/providers; HttpOnly; SameSite=Strict; Max-Age=86400${request.protocol === 'https' ? '; Secure' : ''}`);
    return { id: nextId, ...next };
  }

  mutation(request: FastifyRequest, reply: FastifyReply) {
    const current = this.get(request, reply);
    const supplied = request.headers['x-csrf-token'];
    if (typeof supplied !== 'string' || !/^[0-9a-f]{64}$/.test(supplied)
      || !timingSafeEqual(Buffer.from(supplied), Buffer.from(current.token))) {
      throw new ProviderError('Reload provider settings before continuing.', 403);
    }
    return current.id;
  }
}
