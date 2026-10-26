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
  app.post<{ Body: { requestId: string; connectionId: string; tokenRevision: number; userId: number; repository: { id: number; owner: string; name: string }; branch: string } }>('/github/imports', {
    bodyLimit: 32768, schema: { body: { type: 'object', required: ['requestId', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch'], properties: { requestId: uuid, connectionId: uuid, tokenRevision: { type: 'integer', minimum: 1 }, userId: { type: 'integer', minimum: 1 }, repository: { type: 'object', required: ['id', 'owner', 'name'], properties: { id: { type: 'integer', minimum: 1 }, owner: { type: 'string', maxLength: 39 }, name: { type: 'string', maxLength: 100 } } }, branch: { type: 'string', maxLength: 255 } } } },
    preValidation: async (request) => {
      const body = request.body as Record<string, unknown> | null;
      if (!body || Object.keys(body).some((key) => !['requestId', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch'].includes(key))) throw new ProjectError('Unexpected import fields.', 400);
      if (body.repository && typeof body.repository === 'object' && Object.keys(body.repository).some((key) => !['id', 'owner', 'name'].includes(key))) throw new ProjectError('Unexpected repository fields.', 400);
    },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const { requestId, ...input } = request.body;
    return gitHost({ operation: 'submit', projectId: requestId, requestId, kind: 'import', input });
  });
  app.post<{ Params: { requestId: string }; Body: Record<string, unknown> }>('/github/imports/:requestId/finish', {
    bodyLimit: 32768, schema: { params: { type: 'object', required: ['requestId'], properties: { requestId: uuid } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return projectStore(directory, { operation: 'finish', id: request.params.requestId, input: request.body }, 'github_import');
  });
  app.get<{ Params: { id: string } }>('/:id/github', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    await projectStore(directory, { operation: 'get_settings', id: request.params.id });
    const job = await gitHost({ operation: 'last_job', projectId: request.params.id }).catch(() => null);
    return { binding: await projectBinding(directory, request.params.id), job };
  });
  app.post<{ Params: { id: string }; Body: { requestId: string; kind: string; input: Record<string, unknown> } }>('/:id/github/jobs', {
    bodyLimit: 32768, preValidation: async (request) => {
      if (!request.body || typeof request.body !== 'object' || Array.isArray(request.body) || Object.keys(request.body).some((key) => !['requestId', 'kind', 'input'].includes(key))) throw new ProjectError('Unexpected Git job request fields.', 400);
    }, schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'kind', 'input'], properties: {
      requestId: uuid, kind: { type: 'string', enum: ['initialize', 'status', 'check', 'diff', 'bind', 'create_repository'] }, input: { type: 'object' },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    const { kind, input } = request.body;
    const keys = kind === 'bind' ? ['expectedRevision', 'connectionId', 'tokenRevision', 'userId', 'repository', 'branch', 'author']
      : kind === 'create_repository' ? ['connectionId', 'tokenRevision', 'userId', 'repositoryName', 'private', 'owner'] : kind === 'diff' ? ['path', 'snapshot'] : [];
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
