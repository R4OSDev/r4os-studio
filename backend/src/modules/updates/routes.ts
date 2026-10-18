import type { FastifyInstance } from 'fastify';
import { updateCommand, unavailableStatus } from './client.js';
import { UpdateSessions } from './sessions.js';

export async function updateRoutes(app: FastifyInstance) {
  const sessions = new UpdateSessions();
  app.addHook('onRequest', async (request, reply) => sessions.validate(request, reply));
  app.get('/', async (request, reply) => {
    const session = sessions.session(request, reply, true);
    const status = await updateCommand('status').catch(() => unavailableStatus());
    return { ...status, csrfToken: session.token };
  });
  app.post('/check', { schema: { body: { type: 'object', additionalProperties: false } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return reply.code(202).send(await updateCommand('check'));
  });
  app.post<{ Body: { tag: string; commit: string } }>('/install', { schema: { body: {
    type: 'object', additionalProperties: false, required: ['tag', 'commit'], properties: {
      tag: { type: 'string', pattern: '^v[0-9]+\\.[0-9]+\\.[0-9]+$' },
      commit: { type: 'string', pattern: '^[a-f0-9]{40}$' },
    },
  } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return reply.code(202).send(await updateCommand('install', request.body));
  });
}
