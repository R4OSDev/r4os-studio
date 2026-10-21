import { hostname, networkInterfaces } from 'node:os';
import type { FastifyInstance } from 'fastify';
import type { ProjectsResponse } from '../../../../shared/projects.js';
import { listProjects } from './store.js';

export async function projectRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const hosts = new Set(['localhost', '127.0.0.1', '::1', '[::1]', hostname(),
    ...Object.values(networkInterfaces()).flatMap((items) => (items ?? []).map((item) => item.address)),
    ...(process.env.STUDIO_ALLOWED_HOSTS ?? '').split(',').map((host) => host.trim()).filter(Boolean)]);

  app.addHook('onRequest', async (request, reply) => {
    reply.header('Cache-Control', 'no-store');
    if (!hosts.has(request.hostname)) return reply.code(403).send({ message: 'This host is not allowed to access projects.' });
    if (request.headers['sec-fetch-site'] === 'cross-site') return reply.code(403).send({ message: 'Cross-origin project requests are not allowed.' });
    if (request.headers.origin) {
      let origin: URL;
      try { origin = new URL(request.headers.origin); }
      catch { return reply.code(403).send({ message: 'Invalid request origin.' }); }
      if (origin.origin !== new URL(`${request.protocol}://${request.headers.host}`).origin) {
        return reply.code(403).send({ message: 'Cross-origin project requests are not allowed.' });
      }
    }
  });

  app.get<{ Reply: ProjectsResponse | { message: string } }>('/', async (_request, reply) => {
    try { return { projects: await listProjects(directory) }; }
    catch (error) {
      app.log.error(error, 'Project inventory could not be read.');
      return reply.code(503).send({ message: 'Projects could not be loaded.' });
    }
  });
}
