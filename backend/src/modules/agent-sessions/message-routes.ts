import type { FastifyInstance } from 'fastify';
import type { SessionMessageInput } from '../../../../shared/agent-messages.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const integer = { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
type Params = { id: string; sessionId: string };

export function messageRoutes(app: FastifyInstance, security: ProjectSessions, ownerType: 'project' | 'skill') {
  const base = '/:id/sessions/:sessionId/messages';
  const owner = (id: string) => ownerType === 'skill' ? { ownerType, ownerId: id } : { projectId: id };
  app.get<{ Params: Params; Querystring: { before?: number; view?: 'all' | 'pending' } }>(base, {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: { before: integer, view: { type: 'string', enum: ['all','pending'] } } } },
  }, async (request, reply) => {
    security.session(request, reply); reply.header('Cache-Control', 'private, no-store');
    return agentHost({ operation: 'messages', ...owner(request.params.id), sessionId: request.params.sessionId, before: request.query.before, view: request.query.view });
  });
  app.get<{ Params: Params & { requestId: string } }>(base + '/:requestId', {
    schema: { params: { ...params, required: [...params.required, 'requestId'], properties: { ...params.properties, requestId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply); reply.header('Cache-Control', 'private, no-store');
    return agentHost({ operation: 'message_receipt', ...owner(request.params.id), sessionId: request.params.sessionId, requestId: request.params.requestId });
  });
  app.post<{ Params: Params; Body: SessionMessageInput }>(base, { bodyLimit: 72 * 1024,
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision', 'mode', 'text'], properties: {
      requestId: identity, revision: integer, mode: { type: 'string', enum: ['queue', 'steer'] }, text: { type: 'string', maxLength: 65536 },
      attachments: { type: 'array', maxItems: 8, uniqueItems: true, items: identity },
      target: { type: 'object', additionalProperties: false, required: ['runId', 'threadId', 'turnId'], properties: {
        runId: identity, threadId: { type: 'string', minLength: 1, maxLength: 256 }, turnId: { type: 'string', minLength: 1, maxLength: 256 },
      } },
    } } },
  }, async (request, reply) => {
    security.mutation(request, reply); reply.header('Cache-Control', 'private, no-store');
    const message = await agentHost({ operation: 'submit_message', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body });
    return reply.code(202).send({ message });
  });
  app.post<{ Params: Params; Body: { requestId: string; revision: number; action: 'resume' | 'cancel'; messageId?: string } }>(base + '/control', {
    bodyLimit: 2048, schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision', 'action'], properties: {
      requestId: identity, revision: integer, action: { type: 'string', enum: ['resume', 'cancel'] }, messageId: identity,
    } } },
  }, async (request, reply) => {
    security.mutation(request, reply); reply.header('Cache-Control', 'private, no-store');
    return agentHost({ operation: 'message_control', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body });
  });
}
