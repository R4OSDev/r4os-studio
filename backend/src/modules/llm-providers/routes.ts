import type { FastifyInstance } from 'fastify';
import { ProviderManager } from './service.js';
import type { ProviderOptions } from './service.js';
import { ProviderSessions } from './sessions.js';
import type { ResetRequest } from '../../../../shared/llm-providers.js';
import { chatgptPlanRoutes } from './chatgpt-plan-routes.js';
import { apiProviderRoutes } from './api-routes.js';
import { claudeProviderRoutes } from './claude-routes.js';
import { agentHost } from '../agent-sessions/host.js';
import { NativeAccessServer } from './openai/access-server.js';

export async function providerRoutes(app: FastifyInstance, options: ProviderOptions) {
  const manager = new ProviderManager({ ...options,
    prepareStudio: (id, name, binding) => agentHost({ operation: 'api_provider', action: 'native_connect', id, name, binding }),
    beforeDisconnect: async id => {
      if ((await manager.list()).find(p => p.id === id)?.runtime === 'studio') {
        await agentHost({ operation: 'api_provider', action: 'native_retire', id });
      }
      await options.beforeDisconnect?.(id);
    },
    beforeRemove: async id => {
      if ((await manager.list()).find(p => p.id === id)?.runtime === 'studio') {
        await agentHost({ operation: 'api_provider', action: 'native_retire', id, remove: true });
      }
      await options.beforeRemove?.(id);
    },
  });
  const access = new NativeAccessServer(options.directory, manager);
  app.addHook('onReady', async () => { await manager.list(); await access.start(); });
  app.addHook('onClose', async () => { await access.close(); await manager.close(); });
  const sessions = new ProviderSessions();
  app.addHook('onRequest', async (request, reply) => sessions.validateRequest(request, reply));
  apiProviderRoutes(app, sessions);
  chatgptPlanRoutes(app, sessions);
  claudeProviderRoutes(app, sessions);

  app.get('/', async (request, reply) => {
    const current = sessions.get(request, reply, true);
    return { providers: await manager.list(), csrfToken: current.token, signInAvailable: await manager.available() };
  });
  app.post<{ Body: { name: string; type: 'openai'; runtime?: 'native' | 'studio' } }>('/', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['name', 'type'], properties: {
      name: { type: 'string', minLength: 1, maxLength: 80 }, type: { type: 'string', enum: ['openai'] },
      runtime: { type: 'string', enum: ['native', 'studio'] },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const provider = await manager.create(request.body.name, request.body.runtime);
    return reply.code(201).send({ provider });
  });
  app.get<{ Params: { id: string } }>('/:id', async (request, reply) => {
    sessions.get(request, reply);
    return { provider: await manager.get(request.params.id) };
  });
  app.get<{ Params: { id: string }; Querystring: { refresh?: boolean } }>('/:id/usage', {
    schema: { querystring: { type: 'object', additionalProperties: false, properties: { refresh: { type: 'boolean' } } } },
  }, async (request, reply) => {
    sessions.get(request, reply);
    return { usage: await manager.usage(request.params.id, request.query.refresh === true) };
  });
  app.post<{ Params: { id: string }; Body: ResetRequest }>('/:id/usage/resets', {
    schema: { body: { type: 'object', additionalProperties: false, required: ['confirm', 'idempotencyKey'], properties: {
      confirm: { type: 'boolean', enum: [true] },
      idempotencyKey: { type: 'string', pattern: '^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$' },
      creditId: { type: 'string', minLength: 1, maxLength: 512 },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return await manager.consumeReset(request.params.id, request.body);
  });
  app.post<{ Params: { id: string }; Body?: { flow?: 'browser' | 'deviceCode' } }>('/:id/login', {
    preValidation: async request => { if (request.body === undefined) request.body = {}; },
    schema: { body: { type: 'object', additionalProperties: false, properties: { flow: { type: 'string', enum: ['browser', 'deviceCode'] } } } },
  }, async (request, reply) => {
    const owner = sessions.mutation(request, reply);
    return { login: await manager.start(request.params.id, owner, request.body?.flow) };
  });
  app.post<{ Params: { id: string }; Body: { redirectUrl: string } }>('/:id/login/redirect', {
    bodyLimit: 32768, schema: { body: { type: 'object', additionalProperties: false, required: ['redirectUrl'],
      properties: { redirectUrl: { type: 'string', minLength: 1, maxLength: 16384 } } } },
  }, async (request, reply) => {
    reply.header('Cache-Control', 'private, no-store');
    return { login: await manager.redirect(request.params.id, sessions.mutation(request, reply), request.body.redirectUrl) };
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
  app.post<{ Params: { id: string } }>('/:id/studio', async (request, reply) => {
    sessions.mutation(request, reply);
    return { provider: await manager.prepareStudio(request.params.id) };
  });
  app.delete<{ Params: { id: string } }>('/:id', async (request, reply) => {
    sessions.mutation(request, reply);
    await manager.remove(request.params.id);
    return reply.code(204).send();
  });
}
