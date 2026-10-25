import type { FastifyInstance } from 'fastify';
import type { AgentSession, SessionCreate, SessionHistory, SessionOptions, SessionUpdate } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { sessionStore } from './store.js';
import { developmentHost } from '../project-development/host.js';
import { ProjectError } from '../projects/store.js';
import type { DevelopmentJobPage } from '../../../../shared/project-development.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const fields = {
  name: { type: 'string', minLength: 1, maxLength: 120 }, providerId: identity,
  model: { type: 'string', minLength: 1, maxLength: 120 }, effort: { type: 'string', minLength: 1, maxLength: 30 },
  fastMode: { type: 'boolean' },
};
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
const projectParams = { type: 'object', required: ['id'], properties: { id: identity } };
type SessionParams = { id: string; sessionId: string };

export function agentSessionRoutes(app: FastifyInstance, directory: string, security: ProjectSessions, providers?: string, ownerType: 'project' | 'skill' = 'project') {
  const route = '/:id/sessions';
  const owner = (id: string) => ownerType === 'skill' ? { ownerType, ownerId: id } : { projectId: id };
  if (ownerType === 'project') app.get<{ Params: SessionParams & { jobId: string; evidenceId: string } }>(route + '/:sessionId/images/:jobId/:evidenceId', {
    schema: { params: { ...params, required: ['id', 'sessionId', 'jobId', 'evidenceId'],
      properties: { ...params.properties, jobId: identity, evidenceId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    const { id, sessionId, jobId, evidenceId } = request.params;
    await sessionStore<AgentSession>(directory, { operation: 'get', projectId: id, sessionId }, providers);
    type Image = { metadata: { kind: string; id: string; projectId: string; jobId: string; bytes: number }; base64: string };
    const read = { operation: 'evidence', projectId: id, id: jobId, evidenceId };
    let image: Image;
    try { image = await developmentHost<Image>({ ...read, presentationSessionId: sessionId }); }
    catch (error) {
      if (!(error instanceof ProjectError) || error.statusCode !== 400 || error.message !== 'Unsupported development coordinator operation.') throw error;
      // Older coordinators keep their live workers. Establish session ownership
      // with a read before fetching exactly the same immutable image once.
      const page = await developmentHost<DevelopmentJobPage>({ operation: 'read_job', projectId: id, id: jobId });
      if (page.job.sessionId !== sessionId) throw new ProjectError('This screenshot belongs to another session.', 403);
      image = await developmentHost<Image>(read);
    }
    if (image.metadata.kind !== 'screenshot' || image.metadata.id !== evidenceId || image.metadata.projectId !== id || image.metadata.jobId !== jobId
      || !Number.isSafeInteger(image.metadata.bytes) || image.metadata.bytes < 1 || image.metadata.bytes > 393216)
      throw new ProjectError('This reference is not a session screenshot.', 403);
    return reply.header('Cache-Control', 'private, no-store').header('X-Content-Type-Options', 'nosniff')
      .header('Content-Disposition', 'inline; filename="screenshot.png"').type('image/png').send(Buffer.from(image.base64, 'base64'));
  });
  app.get<{ Params: { id: string } }>(route + '/options', { schema: { params: projectParams } }, async (request, reply) => {
    security.session(request, reply);
    const result = await sessionStore<SessionOptions>(directory, { operation: 'options', ...owner(request.params.id) }, providers);
    if (ownerType === 'project') result.development = await developmentHost<NonNullable<SessionOptions['development']>>({ operation: 'options', ...owner(request.params.id) }).catch(() => undefined);
    return result;
  });
  app.get<{ Params: { id: string } }>(route, { schema: { params: projectParams } }, async (request, reply) => {
    security.session(request, reply);
    return { sessions: await sessionStore<AgentSession[]>(directory, { operation: 'list', ...owner(request.params.id) }, providers) };
  });
  app.post<{ Params: { id: string }; Body: SessionCreate }>(route, { bodyLimit: 16 * 1024,
    schema: { params: projectParams, body: { type: 'object', additionalProperties: false, required: ['name', 'providerId', 'model', 'effort', 'requestId'], properties: { ...fields, requestId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const session = await sessionStore<AgentSession>(directory, { operation: 'create', ...owner(request.params.id), input: request.body }, providers);
    return reply.code(201).send({ session });
  });
  app.get<{ Params: SessionParams }>(route + '/:sessionId', { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return { session: await sessionStore<AgentSession>(directory, { operation: 'get', ...owner(request.params.id), sessionId: request.params.sessionId }, providers) };
  });
  app.patch<{ Params: SessionParams; Body: SessionUpdate }>(route + '/:sessionId/settings', { bodyLimit: 16 * 1024,
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['revision'], minProperties: 2, properties: {
      ...fields, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      permissions: { type: 'object', additionalProperties: { type: 'boolean' }, minProperties: 9, maxProperties: 18 },
    } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return { session: await sessionStore<AgentSession>(directory, { operation: 'update', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body }, providers) };
  });
  app.get<{ Params: SessionParams; Querystring: { before?: number; limit?: number } }>(route + '/:sessionId/history', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: {
      before: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, limit: { type: 'integer', minimum: 1, maximum: 100 },
    } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return sessionStore<SessionHistory>(directory, { operation: 'history', ...owner(request.params.id), sessionId: request.params.sessionId, ...request.query }, providers);
  });
}
