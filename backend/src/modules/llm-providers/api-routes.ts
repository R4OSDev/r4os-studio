import type { FastifyInstance } from 'fastify';
import { agentHost } from '../agent-sessions/host.js';
import type { ProviderSessions } from './sessions.js';
import type { ApiProvider, ApiProviderCreate, ApiProviderUpdate, ApiProviderMutation } from '../../../../shared/api-providers.js';
import { ProviderError } from './errors.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const revision = { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER };
const fields = {
  requestId: uuid, name: { type: 'string', minLength: 1, maxLength: 80 },
  baseUrl: { type: 'string', minLength: 1, maxLength: 2048 },
  protocol: { type: 'string', enum: ['responses', 'chat-completions'] },
  auth: { type: 'string', enum: ['none', 'bearer'] },
};
const params = { type: 'object', required: ['id'], additionalProperties: false, properties: { id: uuid } };
const retiring = { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision'], properties: { requestId: uuid, revision } } };
function input(value: unknown, allowed: string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ProviderError('Invalid API provider input.');
  for (const [field, item] of Object.entries(value)) {
    if (!allowed.includes(field) || (field === 'revision' ? typeof item !== 'number' || !Number.isSafeInteger(item)
      : field === 'enabled' ? typeof item !== 'boolean' : field === 'key' && item === null ? false : typeof item !== 'string')) {
      throw new ProviderError('Invalid API provider fields.');
    }
  }
}

/** These fixed operations never forward a request to a caller-chosen URL. */
export function apiProviderRoutes(app: FastifyInstance, sessions: ProviderSessions) {
  const base = '/api-connections';
  app.get(base, async (request, reply) => {
    sessions.get(request, reply);
    return { providers: await agentHost<ApiProvider[]>({ operation: 'api_provider', action: 'list' }) };
  });
  app.post<{ Body: ApiProviderCreate }>(base, {
    bodyLimit: 16384,
    preValidation: async request => input(request.body, [...Object.keys(fields), 'kind', 'key']),
    schema: { body: { type: 'object', additionalProperties: false, required: ['requestId','name','kind','baseUrl','protocol','auth'], properties: {
      ...fields, kind: { type: 'string', enum: ['openrouter','openai-compatible','local'] }, key: { type: 'string', minLength: 1, maxLength: 8192 },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return reply.code(201).send(await agentHost<ApiProviderMutation>({ operation: 'api_provider', action: 'create', input: request.body }));
  });
  app.get<{ Params: { id: string } }>(base + '/:id', { schema: { params } }, async (request, reply) => {
    sessions.get(request, reply);
    return { provider: await agentHost<ApiProvider>({ operation: 'api_provider', action: 'get', id: request.params.id }) };
  });
  app.patch<{ Params: { id: string }; Body: ApiProviderUpdate }>(base + '/:id', {
    preValidation: async request => input(request.body, [...Object.keys(fields), 'revision', 'key', 'enabled']),
    bodyLimit: 16384, schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId','revision'], properties: {
      ...fields, revision, key: { anyOf: [{ type: 'string', minLength: 1, maxLength: 8192 }, { type: 'null' }] }, enabled: { type: 'boolean' },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return agentHost<ApiProviderMutation>({ operation: 'api_provider', action: 'update', id: request.params.id, input: request.body });
  });
  app.get<{ Params: { id: string; requestId: string } }>(base + '/:id/requests/:requestId', {
    schema: { params: { type: 'object', required: ['id','requestId'], additionalProperties: false, properties: { id: uuid, requestId: uuid } } },
  }, async (request, reply) => {
    sessions.get(request, reply);
    return agentHost<ApiProviderMutation>({ operation: 'api_provider', action: 'receipt', id: request.params.id, requestId: request.params.requestId });
  });
  app.post<{ Params: { id: string }; Body: { requestId: string; revision: number } }>(base + '/:id/disconnect', {
    preValidation: async request => input(request.body, ['requestId', 'revision']),
    bodyLimit: 1024, schema: retiring,
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return agentHost<ApiProviderMutation>({ operation: 'api_provider', action: 'disconnect', id: request.params.id, input: request.body });
  });
  app.delete<{ Params: { id: string }; Body: { requestId: string; revision: number } }>(base + '/:id', {
    preValidation: async request => input(request.body, ['requestId', 'revision']),
    bodyLimit: 1024, schema: retiring,
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return agentHost<ApiProviderMutation>({ operation: 'api_provider', action: 'delete', id: request.params.id, input: request.body });
  });
}
