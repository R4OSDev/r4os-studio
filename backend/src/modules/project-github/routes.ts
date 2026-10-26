import type { FastifyInstance } from 'fastify';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError, projectStore } from '../projects/store.js';
import { gitHost } from './client.js';
import { projectBinding } from '../github-connections/references.js';

export async function projectGithubRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
  const params = { type: 'object', required: ['id'], properties: { id: uuid, requestId: uuid } };
  app.get('/github/capabilities', async (request, reply) => {
    sessions.session(request, reply);
    return gitHost({ operation: 'capabilities' }).catch(() => ({ available: false, protocol: 1, reason: 'Git host support is unavailable.' }));
  });
  app.get<{ Params: { id: string } }>('/:id/github', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    await projectStore(directory, { operation: 'get_settings', id: request.params.id });
    return { binding: await projectBinding(directory, request.params.id) };
  });
  app.post<{ Params: { id: string }; Body: { requestId: string; kind: string; input: Record<string, unknown> } }>('/:id/github/jobs', {
    bodyLimit: 32768, preValidation: async (request) => {
      if (!request.body || typeof request.body !== 'object' || Array.isArray(request.body) || Object.keys(request.body).some((key) => !['requestId', 'kind', 'input'].includes(key))) throw new ProjectError('Unexpected Git job request fields.', 400);
    }, schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'kind', 'input'], properties: {
      requestId: uuid, kind: { type: 'string', enum: ['initialize', 'status', 'check', 'bind'] }, input: { type: 'object' },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const { kind, input } = request.body;
    const keys = kind === 'bind' ? ['expectedRevision', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch', 'author'] : [];
    if (Object.keys(input).some((key) => !keys.includes(key))) throw new ProjectError('Unexpected Git job fields.', 400);
    return gitHost({ operation: 'submit', projectId: request.params.id, ...request.body });
  });
  app.get<{ Params: { id: string; requestId: string } }>('/:id/github/jobs/:requestId', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    return gitHost({ operation: 'job', projectId: request.params.id, requestId: request.params.requestId });
  });
  app.post<{ Params: { id: string; requestId: string } }>('/:id/github/jobs/:requestId/stop', { schema: { params, body: { type: 'object', additionalProperties: false } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return gitHost({ operation: 'cancel', projectId: request.params.id, requestId: request.params.requestId });
  });
  app.post<{ Params: { id: string; requestId: string } }>('/:id/github/jobs/:requestId/reconcile', { schema: { params, body: { type: 'object', additionalProperties: false } } }, async (request, reply) => {
    sessions.mutation(request, reply);
    return gitHost({ operation: 'reconcile', projectId: request.params.id, requestId: request.params.requestId });
  });
}
