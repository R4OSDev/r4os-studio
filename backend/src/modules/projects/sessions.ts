import { randomBytes, timingSafeEqual } from 'node:crypto';
import { hostname, networkInterfaces } from 'node:os';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { ProjectError } from './store.js';

export class ProjectSessions {
  constructor(private scope: 'projects' | 'settings' | 'github' = 'projects') {}
  private sessions = new Map<string, { token: string; expires: number }>();
  private hosts = new Set(['localhost', '127.0.0.1', '::1', '[::1]', hostname(),
    ...Object.values(networkInterfaces()).flatMap((items) => (items ?? []).map((item) => item.address)),
    ...(process.env.STUDIO_ALLOWED_HOSTS ?? '').split(',').map((host) => host.trim()).filter(Boolean)]);

  validate(request: FastifyRequest, reply: FastifyReply) {
    reply.header('Cache-Control', 'no-store');
    if (!this.hosts.has(request.hostname)) throw new ProjectError('This host is not allowed to manage ' + this.scope + '.', 403);
    if (request.headers['sec-fetch-site'] === 'cross-site') throw new ProjectError('Cross-origin requests are not allowed.', 403);
    if (request.headers.origin) {
      let origin: URL;
      try { origin = new URL(request.headers.origin); } catch { throw new ProjectError('Invalid request origin.', 403); }
      if (origin.origin !== new URL(`${request.protocol}://${request.headers.host}`).origin) throw new ProjectError('Cross-origin requests are not allowed.', 403);
    }
  }
  session(request: FastifyRequest, reply: FastifyReply, create = false) {
    const cookie = `studio_${this.scope === 'projects' ? 'project' : this.scope}_session=`;
    const id = request.headers.cookie?.split(';').map((s) => s.trim()).find((s) => s.startsWith(cookie))?.slice(cookie.length);
    const existing = id && this.sessions.get(id);
    if (existing && existing.expires > Date.now()) return existing;
    if (!create) throw new ProjectError('Reload ' + (this.scope === 'projects' ? 'Projects' : 'Settings') + ' before continuing.', 403);
    for (const [key, value] of this.sessions) if (value.expires < Date.now()) this.sessions.delete(key);
    if (this.sessions.size >= 256) this.sessions.delete(this.sessions.keys().next().value!);
    const nextId = randomBytes(32).toString('hex');
    const next = { token: randomBytes(32).toString('hex'), expires: Date.now() + 86400_000 };
    this.sessions.set(nextId, next);
    reply.header('Set-Cookie', `${cookie}${nextId}; Path=/api/${this.scope}; HttpOnly; SameSite=Strict; Max-Age=86400${request.protocol === 'https' ? '; Secure' : ''}`);
    return next;
  }
  mutation(request: FastifyRequest, reply: FastifyReply) {
    const session = this.session(request, reply), token = request.headers['x-csrf-token'];
    if (typeof token !== 'string' || !/^[a-f0-9]{64}$/.test(token) || !timingSafeEqual(Buffer.from(token), Buffer.from(session.token))) {
      throw new ProjectError('Reload ' + (this.scope === 'projects' ? 'Projects' : 'Settings') + ' before continuing.', 403);
    }
  }
}
