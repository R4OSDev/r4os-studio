import type { FastifyInstance } from 'fastify';
import { agentHost } from '../agent-sessions/host.js';
import type { ProviderSessions } from './sessions.js';
import type { ApiProvider, ApiProviderCreate, ApiProviderUpdate, ApiProviderMutation, ApiModelCatalog, ApiModelFacts, ApiModelMutation } from '../../../../shared/api-providers.js';
import { ProviderError } from './errors.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const revision = { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER };
const providerSlugs = { type: 'array', maxItems: 16, uniqueItems: true, items: { type: 'string', minLength: 1, maxLength: 120 } };
const openrouter = { type: 'object', additionalProperties: false, properties: {
  order: providerSlugs, only: providerSlugs, allowFallbacks: { type: 'boolean' },
  attribution: { anyOf: [{ type: 'null' }, { type: 'object', additionalProperties: false, required: ['url', 'title'], properties: {
    url: { type: 'string', minLength: 1, maxLength: 512 }, title: { type: 'string', minLength: 1, maxLength: 80 },
  } }] },
} };
const fields = {
  requestId: uuid, name: { type: 'string', minLength: 1, maxLength: 80 },
  baseUrl: { type: 'string', minLength: 1, maxLength: 2048 },
  protocol: { type: 'string', enum: ['responses', 'chat-completions'] },
  auth: { type: 'string', enum: ['none', 'bearer'] },
  openrouter,
};
const params = { type: 'object', required: ['id'], additionalProperties: false, properties: { id: uuid } };
const retiring = { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision'], properties: { requestId: uuid, revision } } };
const originalParams = { type: 'object', required: ['id', 'requestId'], additionalProperties: false, properties: { id: uuid, requestId: uuid } };
const tokenLimit = { anyOf: [{ type: 'integer', minimum: 1, maximum: 2147483647 }, { type: 'null' }] };
const efforts = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh'];
const capabilityNames = ['text', 'functionTools', 'streaming', 'imageInput', 'reasoning', 'webSearch', 'imageGeneration', 'goals'];
function modelInput(value: unknown, manual: boolean) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ProviderError('Invalid model input.');
  const body = value as Record<string, unknown>;
  for (const [key, item] of Object.entries(body)) {
    if (key === 'model' && manual) continue;
    if (key === 'requestId' ? typeof item !== 'string' : !['providerRevision', ...(manual ? ['catalogRevision'] : [])].includes(key)
      || typeof item !== 'number' || !Number.isSafeInteger(item)) throw new ProviderError('Invalid model fields.');
  }
  if (!manual) return;
  const model = body.model;
  if (!model || typeof model !== 'object' || Array.isArray(model)) throw new ProviderError('Invalid model facts.');
  for (const [key, item] of Object.entries(model)) {
    if (['id', 'name', 'defaultEffort'].includes(key) ? typeof item !== 'string' && !(key === 'defaultEffort' && item === null)
      : ['contextWindow', 'maxOutputTokens'].includes(key) ? item !== null && (typeof item !== 'number' || !Number.isSafeInteger(item))
        : key === 'efforts' ? !Array.isArray(item) || item.some(v => typeof v !== 'string')
          : key === 'capabilities' ? !item || typeof item !== 'object' || Array.isArray(item) || Object.values(item).some(v => typeof v !== 'string') : true) {
      throw new ProviderError('Invalid model facts.');
    }
  }
}
function input(value: unknown, allowed: string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ProviderError('Invalid API provider input.');
  for (const [field, item] of Object.entries(value)) {
    if (field === 'openrouter' && allowed.includes(field)) { routingInput(item); continue; }
    if (!allowed.includes(field) || (field === 'revision' ? typeof item !== 'number' || !Number.isSafeInteger(item)
      : field === 'enabled' ? typeof item !== 'boolean' : field === 'key' && item === null ? false : typeof item !== 'string')) {
      throw new ProviderError('Invalid API provider fields.');
    }
  }
}

function routingInput(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new ProviderError('Invalid OpenRouter input.');
  for (const [key, item] of Object.entries(value)) {
    if (['order', 'only'].includes(key) ? !Array.isArray(item) || item.some(v => typeof v !== 'string')
      : key === 'allowFallbacks' ? typeof item !== 'boolean'
        : key === 'attribution' ? item !== null && (!item || typeof item !== 'object' || Array.isArray(item)
          || Object.entries(item).some(([field, entry]) => !['url', 'title'].includes(field) || typeof entry !== 'string')) : true) {
      throw new ProviderError('Invalid OpenRouter fields.');
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
  app.get<{ Params: { requestId: string } }>(base + '/creation-requests/:requestId', {
    schema: { params: { type: 'object', required: ['requestId'], additionalProperties: false, properties: { requestId: uuid } } },
  }, async (request, reply) => {
    sessions.get(request, reply);
    return agentHost<ApiProviderMutation>({ operation: 'api_provider', action: 'creation_receipt', requestId: request.params.requestId });
  });
  app.get<{ Params: { id: string } }>(base + '/:id/models', { schema: { params } }, async (request, reply) => {
    sessions.get(request, reply);
    return agentHost<ApiModelCatalog>({ operation: 'api_provider', action: 'models', id: request.params.id });
  });
  app.post<{ Params: { id: string }; Body: { requestId: string; providerRevision: number } }>(base + '/:id/models/check', {
    bodyLimit: 1024, preValidation: async request => modelInput(request.body, false),
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'providerRevision'], properties: { requestId: uuid, providerRevision: revision } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return agentHost<ApiModelMutation>({ operation: 'api_provider', action: 'catalog_refresh', id: request.params.id, input: request.body });
  });
  app.post<{ Params: { id: string }; Body: { requestId: string; providerRevision: number; catalogRevision: number; model: ApiModelFacts } }>(base + '/:id/models', {
    bodyLimit: 16384, preValidation: async request => modelInput(request.body, true),
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'providerRevision', 'catalogRevision', 'model'], properties: {
      requestId: uuid, providerRevision: revision, catalogRevision: { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER },
      model: { type: 'object', additionalProperties: false, required: ['id', 'name', 'contextWindow', 'maxOutputTokens', 'capabilities', 'efforts', 'defaultEffort'], properties: {
        id: { type: 'string', minLength: 1, maxLength: 200 }, name: { type: 'string', minLength: 1, maxLength: 200 },
        contextWindow: tokenLimit, maxOutputTokens: tokenLimit,
        capabilities: { type: 'object', additionalProperties: false, required: capabilityNames, properties: Object.fromEntries(capabilityNames.map(key => [key, { type: 'string', enum: ['supported', 'unsupported', 'unknown'] }])) },
        efforts: { type: 'array', maxItems: 6, uniqueItems: true, items: { type: 'string', enum: efforts } },
        defaultEffort: { anyOf: [{ type: 'string', enum: efforts }, { type: 'null' }] },
      } },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return agentHost<ApiModelMutation>({ operation: 'api_provider', action: 'model_save', id: request.params.id, input: request.body });
  });
  app.get<{ Params: { id: string; requestId: string } }>(base + '/:id/model-requests/:requestId', { schema: { params: originalParams } }, async (request, reply) => {
    sessions.get(request, reply);
    return agentHost<ApiModelMutation>({ operation: 'api_provider', action: 'catalog_receipt', id: request.params.id, requestId: request.params.requestId });
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
