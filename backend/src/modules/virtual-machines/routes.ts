import type { FastifyInstance } from 'fastify';
import websocket from '@fastify/websocket';
import { lstat } from 'node:fs/promises';
import { join } from 'node:path';
import { runtimePath, VmError } from './paths.js';
import { ConsoleTickets, ConsoleBridge } from './console.js';
import { PointerControllers } from './pointer.js';
import type { VmInput, VmReleaseChange, VmDevelopmentAccessInput } from '../../../../shared/virtual-machines.js';
import { VmManager, images, defaultImage } from './service.js';
import { VmSessions } from './sessions.js';
import { networkAvailable } from './network.js';
import { qmp } from './qmp.js';
import { withVmLease } from '../project-development/vm-lease.js';
import { developmentVmBridge } from '../project-development/vm-bridge.js';
import { developmentHost } from '../project-development/host.js';

const input = { type: 'object', additionalProperties: false, required: ['name', 'cpus', 'memoryMiB'], properties: {
  name: { type: 'string', minLength: 1, maxLength: 80 }, cpus: { type: 'integer', minimum: 1, maximum: 8 },
  memoryMiB: { type: 'integer', minimum: 2048, maximum: 16384 }, networkEnabled: { type: 'boolean' }, imageId: { type: 'string', pattern: '^[a-zA-Z0-9_.-]{1,100}$' },
} };
export async function vmRoutes(app: FastifyInstance) {
  await app.register(websocket, { options: { maxPayload: 256 * 1024, perMessageDeflate: false } });
  const manager = new VmManager(), sessions = new VmSessions();
  const tickets = new ConsoleTickets(), bridge = new ConsoleBridge(), pointers = new PointerControllers();
  developmentVmBridge(app, manager, bridge, pointers);
  app.addHook('preClose', async () => { bridge.close(); await pointers.close(); });
  app.addHook('preValidation', async (request) => {
    const body = request.body as { networkEnabled?: unknown } | undefined;
    if (body && Object.hasOwn(body, 'networkEnabled') && typeof body.networkEnabled !== 'boolean') throw new VmError('Network must be enabled or disabled.', 400);
  });
  app.addHook('onRequest', async (request, reply) => sessions.validateRequest(request, reply));
  app.get('/', async (request, reply) => {
    const session = sessions.get(request, reply, true);
    const local = await images();
    return { vms: await manager.list(), images: local, defaultImageId: (await defaultImage(local))?.id ?? null,
      csrfToken: session.token, available: await manager.available(), networkAvailable: await networkAvailable() };
  });
  app.post<{ Body: VmInput }>('/', { schema: { body: input } }, async (request, reply) => {
    sessions.mutation(request, reply); return reply.code(201).send({ vm: await manager.create(request.body) });
  });
  app.get<{ Params: { id: string } }>('/:id/development-access', async (request, reply) => {
    sessions.get(request, reply); await manager.config(request.params.id);
    return developmentHost({ operation: 'access_read', vmId: request.params.id });
  });
  app.patch<{ Params: { id: string }; Body: VmDevelopmentAccessInput }>('/:id/development-access', {
    bodyLimit: 4096, schema: { body: { type: 'object', additionalProperties: false,
      required: ['revision', 'vmRevision', 'enabled', 'username'], properties: {
        revision: { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER },
        vmRevision: { type: 'string', minLength: 1, maxLength: 64 }, enabled: { type: 'boolean' },
        username: { type: 'string', maxLength: 32 }, password: { type: 'string', maxLength: 256 }, resetHostKey: { type: 'boolean' },
      } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return withVmLease(request.params.id, async () => {
      await manager.config(request.params.id);
      return developmentHost({ operation: 'access_save', vmId: request.params.id, input: request.body });
    });
  });
  app.post<{ Params: { id: string } }>('/:id/development-access/check', async (request, reply) => {
    sessions.mutation(request, reply); await manager.config(request.params.id);
    // The coordinator holds the cross-process reservation throughout the probe.
    return developmentHost({ operation: 'access_check', vmId: request.params.id });
  });
  app.patch<{ Params: { id: string }; Body: VmInput }>('/:id', { schema: { body: input } }, async (request, reply) => {
    sessions.mutation(request, reply); return { vm: await withVmLease(request.params.id, () => manager.update(request.params.id, request.body)) };
  });
  app.patch<{ Params: { id: string }; Body: VmReleaseChange }>('/:id/release', {
    schema: { body: { type: 'object', additionalProperties: false,
      required: ['confirm', 'expectedRevision', 'expectedImageId', 'expectedImageSha256', 'imageId', 'imageSha256'], properties: {
        confirm: { const: true }, expectedRevision: { type: 'string', minLength: 1, maxLength: 64 },
        expectedImageId: { type: 'string', pattern: '^[a-zA-Z0-9_.-]{1,100}$' }, expectedImageSha256: { type: 'string', pattern: '^[a-f0-9]{64}$' },
        imageId: { type: 'string', pattern: '^[a-zA-Z0-9_.-]{1,100}$' }, imageSha256: { type: 'string', pattern: '^[a-f0-9]{64}$' },
      } } },
  }, async (request, reply) => { sessions.mutation(request, reply); return { vm: await withVmLease(request.params.id, () => manager.changeRelease(request.params.id, request.body)) }; });
  app.delete<{ Params: { id: string }; Body: { confirm: true } }>('/:id', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['confirm'], properties: { confirm: { const: true } } } },
  }, async (request, reply) => { sessions.mutation(request, reply); await withVmLease(request.params.id, () => manager.remove(request.params.id)); return reply.code(204).send(); });
  app.post<{ Params: { id: string }; Body: { action: string } }>('/:id/actions', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['action'], properties: {
      action: { type: 'string', enum: ['start', 'shutdown', 'force-stop', 'restart', 'sync-exchange'] },
    } } },
  }, async (request, reply) => { sessions.mutation(request, reply); return { vm: await withVmLease(request.params.id, () => manager.action(request.params.id, request.body.action)) }; });
  app.get<{ Params: { id: string } }>('/:id/files', async (request, reply) => {
    sessions.get(request, reply); return { files: await manager.files(request.params.id) };
  });
  app.post<{ Params: { id: string }; Body: { name: string; content: string } }>('/:id/files', {
    bodyLimit: 12 * 1024 * 1024, schema: { body: { type: 'object', additionalProperties: false, required: ['name', 'content'], properties: {
      name: { type: 'string', minLength: 1, maxLength: 100 }, content: { type: 'string', maxLength: 12 * 1024 * 1024, pattern: '^[A-Za-z0-9+/]*={0,2}$' },
    } } },
  }, async (request, reply) => { sessions.mutation(request, reply); await withVmLease(request.params.id, () => manager.upload(request.params.id, request.body.name, request.body.content)); return reply.code(204).send(); });
  app.delete<{ Params: { id: string; name: string } }>('/:id/files/:name', async (request, reply) => {
    sessions.mutation(request, reply); await withVmLease(request.params.id, () => manager.removeFile(request.params.id, request.params.name)); return reply.code(204).send();
  });
  app.get<{ Params: { id: string }; Querystring: { name?: 'serial' | 'qemu' } }>('/:id/log', {
    schema: { querystring: { type: 'object', additionalProperties: false, properties: { name: { type: 'string', enum: ['serial', 'qemu'] } } } },
  }, async (request, reply) => { sessions.get(request, reply); return { text: await manager.log(request.params.id, request.query.name ?? 'serial') }; });
  for (const channel of ['display', 'pointer'] as const) {
    app.post<{ Params: { id: string } }>(`/:id/${channel === 'display' ? 'console' : 'pointer'}-ticket`, async (request, reply) => {
      const owner = sessions.mutation(request, reply);
      return withVmLease(request.params.id, async () => {
      const vm = await manager.get(request.params.id);
      if (!['running', 'paused'].includes(vm.state)) throw new VmError('Start the VM before opening its console.');
      try { if (!(await lstat(join(runtimePath(vm.id), channel === 'display' ? 'vnc.sock' : 'qmp.sock'))).isSocket()) throw new Error(); }
      catch { throw new VmError('Stop and start this VM to enable the live console.'); }
      return { ticket: tickets.issue(vm.id, owner!, channel) };
      });
    });
    app.get<{ Params: { id: string } }>(`/:id/${channel === 'display' ? 'console' : 'pointer'}`, {
      websocket: true,
      preValidation: async (request, reply) => {
        if (!request.headers.origin) throw new VmError('A browser origin is required.', 403);
        const owner = sessions.get(request, reply).id;
        await manager.config(request.params.id);
        tickets.consume(request.params.id, owner!, request.headers['sec-websocket-protocol'], channel);
      },
    }, (socket, request) => {
      void withVmLease(request.params.id, async () => {
        if (channel === 'display') bridge.attach(request.params.id, socket); else pointers.attach(request.params.id, socket);
      }).catch(() => socket.close(1008, 'This VM is reserved by a development job.'));
    });
  }
  // A POST because screendump asks QEMU to write a private temporary file.
  app.post<{ Params: { id: string } }>('/:id/screen', async (request, reply) => {
    sessions.mutation(request, reply); return reply.type('image/png').send(await manager.screen(request.params.id));
  });
  app.post<{ Params: { id: string }; Body: { keys: string[] } }>('/:id/keys', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['keys'], properties: {
      keys: { type: 'array', minItems: 1, maxItems: 5, items: { type: 'string', pattern: '^[a-z0-9_-]{1,16}$' } },
    } } },
  }, async (request, reply) => { sessions.mutation(request, reply); await manager.config(request.params.id);
    await withVmLease(request.params.id, () => qmp(request.params.id, 'send-key', { keys: request.body.keys.map((key) => ({ type: 'qcode', data: key })), 'hold-time': 70 })); return reply.code(204).send();
  });
}
