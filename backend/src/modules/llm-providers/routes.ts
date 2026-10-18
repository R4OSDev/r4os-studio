import type { FastifyInstance } from 'fastify';
import { ProviderManager } from './service.js';
import type { ProviderOptions } from './service.js';
import { ProviderSessions } from './sessions.js';

export async function providerRoutes(app: FastifyInstance, options: ProviderOptions) {
  const manager = new ProviderManager(options);
  app.addHook('onClose', () => manager.close());
  const sessions = new ProviderSessions();
  app.addHook('onRequest', async (request, reply) => sessions.validateRequest(request, reply));

  app.get('/', async (request, reply) => {
    const current = sessions.get(request, reply, true);
    return { providers: await manager.list(), csrfToken: current.token, signInAvailable: await manager.available() };
  });
  app.post<{ Body: { name: string; type: 'openai' } }>('/', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['name', 'type'], properties: {
      name: { type: 'string', minLength: 1, maxLength: 80 }, type: { type: 'string', enum: ['openai'] },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const provider = await manager.create(request.body.name);
    return reply.code(201).send({ provider });
  });
  app.get<{ Params: { id: string } }>('/:id', async (request, reply) => {
    sessions.get(request, reply);
    return { provider: await manager.get(request.params.id) };
  });
  app.post<{ Params: { id: string } }>('/:id/login', async (request, reply) => {
    const owner = sessions.mutation(request, reply);
    return { login: await manager.start(request.params.id, owner) };
  });
  app.get<{ Params: { id: string } }>('/:id/login', async (request, reply) => {
    const current = sessions.get(request, reply);
    return { login: await manager.login(request.params.id, current.id) };
  });
  app.delete<{ Params: { id: string } }>('/:id/login', async (request, reply) => {
    await manager.cancel(request.params.id, sessions.mutation(request, reply));
    return reply.code(204).send();
  });
  app.post<{ Params: { id: string } }>('/:id/disconnect', async (request, reply) => {
    sessions.mutation(request, reply);
    return { provider: await manager.disconnect(request.params.id) };
  });
  app.delete<{ Params: { id: string } }>('/:id', async (request, reply) => {
    sessions.mutation(request, reply);
    await manager.remove(request.params.id);
    return reply.code(204).send();
  });
}
