import type { FastifyInstance } from 'fastify';
import type { VmInput } from '../../../../shared/virtual-machines.js';
import { VmManager, images } from './service.js';
import { VmSessions } from './sessions.js';
import { qmp } from './qmp.js';

const input = { type: 'object', additionalProperties: false, required: ['name', 'cpus', 'memoryMiB'], properties: {
  name: { type: 'string', minLength: 1, maxLength: 80 }, cpus: { type: 'integer', minimum: 1, maximum: 8 },
  memoryMiB: { type: 'integer', minimum: 2048, maximum: 16384 }, imageId: { type: 'string', pattern: '^[a-zA-Z0-9_.-]{1,100}$' },
} };
export async function vmRoutes(app: FastifyInstance) {
  const manager = new VmManager(), sessions = new VmSessions();
  app.addHook('onRequest', async (request, reply) => sessions.validateRequest(request, reply));
  app.get('/', async (request, reply) => {
    const session = sessions.get(request, reply, true);
    return { vms: await manager.list(), images: await images(), csrfToken: session.token, available: await manager.available() };
  });
  app.post<{ Body: VmInput }>('/', { schema: { body: input } }, async (request, reply) => {
    sessions.mutation(request, reply); return reply.code(201).send({ vm: await manager.create(request.body) });
  });
  app.patch<{ Params: { id: string }; Body: VmInput }>('/:id', { schema: { body: input } }, async (request, reply) => {
    sessions.mutation(request, reply); return { vm: await manager.update(request.params.id, request.body) };
  });
  app.delete<{ Params: { id: string }; Body: { confirm: true } }>('/:id', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['confirm'], properties: { confirm: { const: true } } } },
  }, async (request, reply) => { sessions.mutation(request, reply); await manager.remove(request.params.id); return reply.code(204).send(); });
  app.post<{ Params: { id: string }; Body: { action: string } }>('/:id/actions', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['action'], properties: {
      action: { type: 'string', enum: ['start', 'shutdown', 'force-stop', 'restart'] },
    } } },
  }, async (request, reply) => { sessions.mutation(request, reply); return { vm: await manager.action(request.params.id, request.body.action) }; });
  app.get<{ Params: { id: string } }>('/:id/files', async (request, reply) => {
    sessions.get(request, reply); return { files: await manager.files(request.params.id) };
  });
  app.post<{ Params: { id: string }; Body: { name: string; content: string } }>('/:id/files', {
    bodyLimit: 12 * 1024 * 1024, schema: { body: { type: 'object', additionalProperties: false, required: ['name', 'content'], properties: {
      name: { type: 'string', minLength: 1, maxLength: 100 }, content: { type: 'string', maxLength: 12 * 1024 * 1024, pattern: '^[A-Za-z0-9+/]*={0,2}$' },
    } } },
  }, async (request, reply) => { sessions.mutation(request, reply); await manager.upload(request.params.id, request.body.name, request.body.content); return reply.code(204).send(); });
  app.delete<{ Params: { id: string; name: string } }>('/:id/files/:name', async (request, reply) => {
    sessions.mutation(request, reply); await manager.removeFile(request.params.id, request.params.name); return reply.code(204).send();
  });
  app.get<{ Params: { id: string }; Querystring: { name?: 'serial' | 'qemu' } }>('/:id/log', {
    schema: { querystring: { type: 'object', additionalProperties: false, properties: { name: { type: 'string', enum: ['serial', 'qemu'] } } } },
  }, async (request, reply) => { sessions.get(request, reply); return { text: await manager.log(request.params.id, request.query.name ?? 'serial') }; });
  // A POST because screendump asks QEMU to write a private temporary file.
  app.post<{ Params: { id: string } }>('/:id/screen', async (request, reply) => {
    sessions.mutation(request, reply); return reply.type('image/png').send(await manager.screen(request.params.id));
  });
  app.post<{ Params: { id: string }; Body: { keys: string[] } }>('/:id/keys', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['keys'], properties: {
      keys: { type: 'array', minItems: 1, maxItems: 5, items: { type: 'string', pattern: '^[a-z0-9_-]{1,16}$' } },
    } } },
  }, async (request, reply) => { sessions.mutation(request, reply); await manager.config(request.params.id);
    await qmp(request.params.id, 'send-key', { keys: request.body.keys.map((key) => ({ type: 'qcode', data: key })), 'hold-time': 70 }); return reply.code(204).send();
  });
}
