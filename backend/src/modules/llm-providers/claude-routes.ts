import type { FastifyInstance } from 'fastify';
import { agentHost } from '../agent-sessions/host.js';
import type { ProviderSessions } from './sessions.js';
import { ProviderError } from './errors.js';
import type { ClaudeProviderCreate, ClaudeProviderMutation, ClaudeProviderRemove, ClaudeSubscriptionProvider, ClaudeAuthRequest, ClaudeAuthOperation, ClaudeRuntimeStatus } from '../../../../shared/claude-subscription.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id'], properties: { id: uuid } };
const original = { type: 'object', additionalProperties: false, required: ['id', 'requestId'], properties: { id: uuid, requestId: uuid } };
function fields(value: unknown, expected: string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !expected.includes(k))
    || Object.entries(value).some(([k, v]) => k === 'revision' ? !Number.isSafeInteger(v) || (v as number) < 1 : typeof v !== 'string')) {
    throw new ProviderError('Invalid Claude subscription request.');
  }
}

/** Fixed native commands only. No generic CLI, OAuth-token or URL endpoint. */
export function claudeProviderRoutes(app: FastifyInstance, sessions: ProviderSessions) {
  const base = '/claude-subscriptions';
  app.get(base, async (request, reply) => {
    sessions.get(request, reply);
    return { providers: await agentHost<ClaudeSubscriptionProvider[]>({ operation: 'claude_provider', action: 'list' }) };
  });
  app.get(base + '/runtime', async (request, reply) => {
    sessions.get(request, reply);
    return agentHost<ClaudeRuntimeStatus>({ operation: 'claude_provider', action: 'runtime' });
  });
  app.post<{ Body: ClaudeProviderCreate }>(base, {
    bodyLimit: 1024, preValidation: async request => fields(request.body, ['requestId', 'name']),
    schema: { body: { type: 'object', additionalProperties: false, required: ['requestId', 'name'], properties: {
      requestId: uuid, name: { type: 'string', minLength: 1, maxLength: 80 },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return reply.code(201).send(await agentHost<ClaudeProviderMutation>({ operation: 'claude_provider', action: 'create', input: request.body }));
  });
  app.get<{ Params: { requestId: string } }>(base + '/creation-requests/:requestId', {
    schema: { params: { type: 'object', additionalProperties: false, required: ['requestId'], properties: { requestId: uuid } } },
  }, async (request, reply) => {
    sessions.get(request, reply);
    return agentHost<ClaudeProviderMutation>({ operation: 'claude_provider', action: 'creation_receipt', requestId: request.params.requestId });
  });
  app.get<{ Params: { id: string } }>(base + '/:id', { schema: { params } }, async (request, reply) => {
    sessions.get(request, reply);
    return { provider: await agentHost<ClaudeSubscriptionProvider>({ operation: 'claude_provider', action: 'get', id: request.params.id }) };
  });
  app.delete<{ Params: { id: string }; Body: ClaudeProviderRemove }>(base + '/:id', {
    bodyLimit: 1024, preValidation: async request => fields(request.body, ['requestId', 'revision', 'confirmName']),
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision', 'confirmName'], properties: {
      requestId: uuid, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      confirmName: { type: 'string', minLength: 1, maxLength: 80 },
    } } },
  }, async (request, reply) => {
    const owner = sessions.mutation(request, reply);
    return agentHost<ClaudeAuthOperation>({ operation: 'claude_provider', action: 'auth_remove', id: request.params.id, owner, input: request.body });
  });
  app.get<{ Params: { id: string } }>(base + '/:id/limits', { schema: { params } }, async (request, reply) => {
    sessions.get(request, reply);
    return { limits: await agentHost({ operation: 'claude_provider', action: 'limits', id: request.params.id }) };
  });
  app.get<{ Params: { id: string } }>(base + '/:id/catalog', { schema: { params } }, async (request, reply) => {
    sessions.get(request, reply);
    return { catalog: await agentHost({ operation: 'claude_provider', action: 'catalog', id: request.params.id }) };
  });
  app.post<{ Params: { id: string }; Body: ClaudeAuthRequest }>(base + '/:id/auth', {
    bodyLimit: 1024, preValidation: async request => fields(request.body, ['requestId', 'revision', 'action']),
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision', 'action'], properties: {
      requestId: uuid, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      action: { type: 'string', enum: ['connect', 'status', 'disconnect', 'limits', 'catalog'] },
    } } },
  }, async (request, reply) => {
    const owner = sessions.mutation(request, reply);
    return agentHost<ClaudeAuthOperation>({ operation: 'claude_provider', action: 'auth_start', id: request.params.id, owner, input: request.body });
  });
  app.get<{ Params: { id: string; requestId: string } }>(base + '/:id/auth-requests/:requestId', { schema: { params: original } }, async (request, reply) => {
    const owner = sessions.get(request, reply).id;
    return agentHost<ClaudeAuthOperation>({ operation: 'claude_provider', action: 'auth_receipt', ...request.params, owner });
  });
  app.post<{ Params: { id: string; requestId: string }; Body: { code: string } }>(base + '/:id/auth-requests/:requestId/code', {
    bodyLimit: 2048, preValidation: async request => fields(request.body, ['code']),
    schema: { params: original, body: { type: 'object', additionalProperties: false, required: ['code'], properties: {
      code: { type: 'string', minLength: 18, maxLength: 1800 },
    } } },
  }, async (request, reply) => {
    const owner = sessions.mutation(request, reply);
    return agentHost<ClaudeAuthOperation>({ operation: 'claude_provider', action: 'auth_code', ...request.params, owner, code: request.body.code });
  });
  app.post<{ Params: { id: string; requestId: string }; Body: Record<string, never> }>(base + '/:id/auth-requests/:requestId/cancel', {
    bodyLimit: 128, preValidation: async request => fields(request.body, []),
    schema: { params: original, body: { type: 'object', additionalProperties: false, maxProperties: 0 } },
  }, async (request, reply) => {
    const owner = sessions.mutation(request, reply);
    return agentHost<ClaudeAuthOperation>({ operation: 'claude_provider', action: 'auth_cancel', ...request.params, owner });
  });
}
