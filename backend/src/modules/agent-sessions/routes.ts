import type { FastifyInstance } from 'fastify';
import type { AgentSession, SessionCreate, SessionHistory, SessionOptions, SessionUpdate } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { sessionStore } from './store.js';
import { developmentHost } from '../project-development/host.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const fields = {
  name: { type: 'string', minLength: 1, maxLength: 120 }, providerId: identity,
  model: { type: 'string', minLength: 1, maxLength: 120 }, effort: { type: 'string', minLength: 1, maxLength: 30 },
};
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
const projectParams = { type: 'object', required: ['id'], properties: { id: identity } };
type SessionParams = { id: string; sessionId: string };

export function agentSessionRoutes(app: FastifyInstance, directory: string, security: ProjectSessions, providers?: string) {
  const route = '/:id/sessions';
  app.get<{ Params: { id: string } }>(route + '/options', { schema: { params: projectParams } }, async (request, reply) => {
    security.session(request, reply);
    const result = await sessionStore<SessionOptions>(directory, { operation: 'options', projectId: request.params.id }, providers);
    result.development = await developmentHost<NonNullable<SessionOptions['development']>>({ operation: 'options', projectId: request.params.id }).catch(() => undefined);
    return result;
  });
  app.get<{ Params: { id: string } }>(route, { schema: { params: projectParams } }, async (request, reply) => {
    security.session(request, reply);
    return { sessions: await sessionStore<AgentSession[]>(directory, { operation: 'list', projectId: request.params.id }, providers) };
  });
  app.post<{ Params: { id: string }; Body: SessionCreate }>(route, { bodyLimit: 16 * 1024,
    schema: { params: projectParams, body: { type: 'object', additionalProperties: false, required: ['name', 'providerId', 'model', 'effort', 'requestId'], properties: { ...fields, requestId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const session = await sessionStore<AgentSession>(directory, { operation: 'create', projectId: request.params.id, input: request.body }, providers);
    return reply.code(201).send({ session });
  });
  app.get<{ Params: SessionParams }>(route + '/:sessionId', { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return { session: await sessionStore<AgentSession>(directory, { operation: 'get', projectId: request.params.id, sessionId: request.params.sessionId }, providers) };
  });
  app.patch<{ Params: SessionParams; Body: SessionUpdate }>(route + '/:sessionId/settings', { bodyLimit: 16 * 1024,
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['revision'], minProperties: 2, properties: {
      ...fields, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      permissions: { type: 'object', additionalProperties: { type: 'boolean' }, minProperties: 9, maxProperties: 16 },
    } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return { session: await sessionStore<AgentSession>(directory, { operation: 'update', projectId: request.params.id, sessionId: request.params.sessionId, input: request.body }, providers) };
  });
  app.get<{ Params: SessionParams; Querystring: { before?: number; limit?: number } }>(route + '/:sessionId/history', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: {
      before: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, limit: { type: 'integer', minimum: 1, maximum: 100 },
    } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return sessionStore<SessionHistory>(directory, { operation: 'history', projectId: request.params.id, sessionId: request.params.sessionId, ...request.query }, providers);
  });
}
