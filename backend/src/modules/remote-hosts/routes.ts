import type { FastifyInstance } from 'fastify';
import type { RemoteHost } from '../../../../shared/remote-hosts.js';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { remoteHostStore } from './store.js';

export async function remoteHostRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions('remote-hosts');
  app.setErrorHandler((error, _request, reply) => {
    const known = error instanceof ProjectError;
    const code = known ? error.statusCode : (error as { statusCode?: number }).statusCode;
    void reply.code(known ? code! : code === 413 ? 413 : code === 400 ? 400 : 503).send({ message: known ? error.message : 'The Remote Host request could not be completed. Existing data was preserved.' });
  });
  app.addHook('onRequest', async (request, reply) => {
    sessions.validate(request, reply);
    if (request.method !== 'GET') sessions.mutation(request, reply);
    else if (request.url.split('?')[0].replace(/\/$/, '') !== '/api/remote-hosts') sessions.session(request, reply);
  });
  app.get('/', async (request, reply) => ({ hosts: await remoteHostStore<RemoteHost[]>(directory, { operation: 'list' }), csrfToken: sessions.session(request, reply, true).token }));
  app.get<{ Params: { id: string } }>('/:id', async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'get', id: request.params.id }));
  app.post('/', { bodyLimit: 16384 }, async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'create', input: request.body }));
  app.patch<{ Params: { id: string } }>('/:id', { bodyLimit: 16384 }, async (request) => remoteHostStore<RemoteHost>(directory, { operation: 'update', id: request.params.id, input: request.body }));
  app.delete<{ Params: { id: string } }>('/:id', { bodyLimit: 4096 }, async (request) => remoteHostStore<{ id: string; removed: true }>(directory, { operation: 'remove', id: request.params.id, input: request.body }));
}
