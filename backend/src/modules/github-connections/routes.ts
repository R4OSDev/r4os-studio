import type { FastifyInstance } from 'fastify';
import { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { GitHubStore, createInput, changeInput, deleteInput, connectionId } from './store.js';

export async function githubRoutes(app: FastifyInstance, { directory }: { directory: string }) {
  const sessions = new ProjectSessions('github'), store = new GitHubStore(directory);
  app.setErrorHandler((error, _request, reply) => {
    const known = error instanceof ProjectError;
    const code = error instanceof Error && 'statusCode' in error ? error.statusCode : 503;
    const status = known ? error.statusCode : (code === 413 ? 413 : code === 400 ? 400 : 503);
    void reply.code(status).send({ message: known ? error.message : status === 413 ? 'Connection request is too large.' : 'The connection request could not be completed.' });
  });
  app.addHook('onRequest', async (request, reply) => {
    sessions.validate(request, reply);
    if (request.method !== 'GET') sessions.mutation(request, reply);
  });
  app.get('/', async (request, reply) => {
    const session = sessions.session(request, reply, true);
    return { connections: await store.list(), csrfToken: session.token };
  });
  app.post('/', { bodyLimit: 16 * 1024 }, async (request) => store.create(createInput(request.body)));
  app.patch<{ Params: { id: string } }>('/:id', { bodyLimit: 16 * 1024 }, async (request) => {
    connectionId(request.params.id); return store.update(request.params.id, changeInput(request.body));
  });
  app.delete<{ Params: { id: string } }>('/:id', async (request, reply) => {
    connectionId(request.params.id); await store.remove(request.params.id, deleteInput(request.body)); return reply.code(204).send();
  });
}
