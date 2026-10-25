import type { FastifyInstance } from 'fastify';
import type { DevelopmentBuildInput, DevelopmentDeployInput, DevelopmentRunInput, DevelopmentSettings, DevelopmentJob, DevelopmentJobPage } from '../../../../shared/project-development.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { developmentHost } from './host.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const revision = { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER };
const params = { type: 'object', additionalProperties: false, required: ['id'], properties: { id: identity } };
const jobParams = { ...params, required: ['id', 'jobId'], properties: { ...params.properties, jobId: identity } };

export function developmentRoutes(app: FastifyInstance, security: ProjectSessions) {
  const base = '/:id/development';
  app.post<{ Params: { id: string; jobId: string }; Body: { requestId: string } }>(base + '/jobs/:jobId/complete', {
    bodyLimit: 1024,
    schema: { params: jobParams, body: { type: 'object', additionalProperties: false,
      required: ['requestId'], properties: { requestId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return developmentHost<DevelopmentJobPage>({ operation: 'complete_check', projectId: request.params.id,
      id: request.params.jobId, input: request.body });
  });
  app.post<{ Params: { id: string; jobId: string }; Body: { requestId: string } }>(base + '/jobs/:jobId/reconcile', {
    bodyLimit: 1024,
    preValidation: async (request) => {
      if (!request.body || typeof request.body !== 'object' || Object.keys(request.body).some((k) => k !== 'requestId')) throw new ProjectError('Unexpected recovery fields.', 400);
    },
    schema: { params: jobParams, body: { type: 'object', additionalProperties: false, required: ['requestId'], properties: { requestId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const result = await developmentHost<{ error?: string; code?: number }>({ operation: 'reconcile', projectId: request.params.id, id: request.params.jobId, input: request.body });
    if (result.error) throw new ProjectError(result.error, result.code);
    return result;
  });
  for (const operation of ['options', 'settings', 'jobs'] as const) {
    app.get<{ Params: { id: string } }>(base + '/' + operation, { schema: { params } }, async (request, reply) => {
      security.session(request, reply);
      return developmentHost({ operation, projectId: request.params.id });
    });
  }
  app.patch<{ Params: { id: string }; Body: DevelopmentSettings }>(base + '/settings', {
    bodyLimit: 16384, schema: { params, body: { type: 'object', additionalProperties: true } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return developmentHost<DevelopmentSettings>({ operation: 'save_settings', projectId: request.params.id, input: request.body });
  });
  for (const operation of ['capture', 'input', 'assess'] as const) {
    const suffix = operation === 'assess' ? 'assessment' : operation;
    app.post<{ Params: { id: string; jobId: string }; Body: Record<string, unknown> }>(base + '/jobs/:jobId/' + suffix, {
      bodyLimit: 16384, schema: { params: jobParams, body: { type: 'object', additionalProperties: true } },
    }, async (request, reply) => {
      security.mutation(request, reply);
      return developmentHost({ operation, projectId: request.params.id, id: request.params.jobId, input: request.body });
    });
  }
  app.get<{ Params: { id: string; jobId: string; evidenceId: string } }>(base + '/jobs/:jobId/evidence/:evidenceId', {
    schema: { params: { ...jobParams, required: ['id', 'jobId', 'evidenceId'], properties: { ...jobParams.properties, evidenceId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    const value = await developmentHost<{ metadata: { kind: string }; base64: string }>({ operation: 'evidence',
      projectId: request.params.id, id: request.params.jobId, evidenceId: request.params.evidenceId });
    return reply.header('Cache-Control', 'private, no-store').header('X-Content-Type-Options', 'nosniff')
      .type(value.metadata.kind === 'screenshot' ? 'image/png' : 'application/octet-stream').send(Buffer.from(value.base64, 'base64'));
  });
  app.get<{ Params: { id: string; jobId: string }; Querystring: { before?: number } }>(base + '/jobs/:jobId/evidence', {
    schema: { params: jobParams, querystring: { type: 'object', additionalProperties: false, properties: { before: revision } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return developmentHost({ operation: 'evidence_history', projectId: request.params.id, id: request.params.jobId, before: request.query.before ?? null });
  });
  app.post<{ Params: { id: string }; Body: DevelopmentBuildInput }>(base + '/builds', {
    bodyLimit: 8192,
    preValidation: async (request) => {
      const value = request.body;
      if (!value || typeof value !== 'object' || Array.isArray(value)
        || Object.keys(value).some((key) => !['requestId', 'projectRevision', 'settingsRevision'].includes(key))) {
        throw new ProjectError('Unexpected development fields.', 400);
      }
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'projectRevision', 'settingsRevision'], properties: { requestId: identity,
        projectRevision: revision, settingsRevision: revision } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const job = await developmentHost<DevelopmentJob>({ operation: 'build', projectId: request.params.id, input: request.body });
    return reply.code(202).send({ job });
  });
  app.post<{ Params: { id: string }; Body: DevelopmentDeployInput }>(base + '/deployments', {
    bodyLimit: 8192,
    preValidation: async (request) => {
      const value = request.body;
      if (!value || typeof value !== 'object' || Array.isArray(value)
        || Object.keys(value).some((key) => !['requestId', 'projectRevision', 'settingsRevision', 'artifactId'].includes(key)))
        throw new ProjectError('Unexpected deployment fields.', 400);
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'projectRevision', 'settingsRevision', 'artifactId'], properties: {
        requestId: identity, projectRevision: revision, settingsRevision: revision, artifactId: identity,
      } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return reply.code(202).send({ job: await developmentHost<DevelopmentJob>({ operation: 'deploy', projectId: request.params.id, input: request.body }) });
  });
  app.post<{ Params: { id: string }; Body: DevelopmentRunInput }>(base + '/executions', {
    bodyLimit: 8192,
    preValidation: async (request) => {
      const value = request.body;
      if (!value || typeof value !== 'object' || Array.isArray(value)
        || Object.keys(value).some((key) => !['requestId', 'projectRevision', 'settingsRevision', 'deploymentId'].includes(key)))
        throw new ProjectError('Unexpected deployment fields.', 400);
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'projectRevision', 'settingsRevision', 'deploymentId'], properties: {
        requestId: identity, projectRevision: revision, settingsRevision: revision, deploymentId: identity,
      } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return reply.code(202).send({ job: await developmentHost<DevelopmentJob>({ operation: 'execution', projectId: request.params.id, input: request.body }) });
  });
  app.get<{ Params: { id: string; deploymentId: string } }>(base + '/deployments/:deploymentId', {
    schema: { params: { ...params, required: ['id', 'deploymentId'], properties: { ...params.properties, deploymentId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return { deployment: await developmentHost({ operation: 'deployment', projectId: request.params.id, id: request.params.deploymentId }) };
  });
  app.get<{ Params: { id: string; jobId: string }; Querystring: { offset?: number } }>(base + '/jobs/:jobId', {
    schema: { params: jobParams, querystring: { type: 'object', additionalProperties: false,
      properties: { offset: { type: 'integer', minimum: 0, maximum: 2097152 } } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return developmentHost<DevelopmentJobPage>({ operation: 'read_job', projectId: request.params.id,
      id: request.params.jobId, offset: request.query.offset ?? 0 });
  });
  app.post<{ Params: { id: string; jobId: string } }>(base + '/jobs/:jobId/stop', {
    schema: { params: jobParams },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return { job: await developmentHost<DevelopmentJob>({ operation: 'stop_job', projectId: request.params.id, id: request.params.jobId }) };
  });
  app.get<{ Params: { id: string; artifactId: string } }>(base + '/artifacts/:artifactId', {
    schema: { params: { ...params, required: ['id', 'artifactId'], properties: { ...params.properties, artifactId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return { artifact: await developmentHost({ operation: 'artifact', projectId: request.params.id, id: request.params.artifactId }) };
  });
}
