import type { FastifyInstance } from 'fastify';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
type Params = { id: string; sessionId: string; requestId?: string };
export function sessionDeletionRoutes(app: FastifyInstance, security: ProjectSessions, ownerType: 'project' | 'skill') {
  const properties = { id: identity, sessionId: identity, requestId: identity };
  const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties };
  const owner = (id: string) => ({ ownerType, ownerId: id });
  async function ready() {
    const capabilities = await agentHost<{ sessionDeletion?: number }>({ operation: 'capabilities' });
    if (capabilities.sessionDeletion !== 1) throw new ProjectError('Session deletion needs updated agent host support.', 503);
  }
  const route = '/:id/sessions/:sessionId/deletion';
  app.get<{ Params: Params }>(route, { schema: { params } }, async (request, reply) => {
    security.session(request, reply); await ready();
    return agentHost({ operation: 'session_delete_preview', ...owner(request.params.id), sessionId: request.params.sessionId });
  });
  app.get<{ Params: Params }>(route + '/:requestId', { schema: { params: { ...params, required: ['id', 'sessionId', 'requestId'] } } }, async (request, reply) => {
    security.session(request, reply); await ready();
    return agentHost({ operation: 'session_delete_receipt', ...owner(request.params.id), sessionId: request.params.sessionId, requestId: request.params.requestId });
  });
  app.post<{ Params: Params; Body: unknown }>(route, { bodyLimit: 2048, schema: { params,
    body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision', 'scopeHash', 'confirmName'],
      properties: { requestId: identity, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
        scopeHash: { type: 'string', pattern: '^[a-f0-9]{64}$' }, confirmName: { type: 'string', minLength: 1, maxLength: 120 } } },
  } }, async (request, reply) => {
    security.mutation(request, reply); await ready();
    const result = await agentHost({ operation: 'session_delete', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body });
    return reply.code(202).send(result);
  });
}
