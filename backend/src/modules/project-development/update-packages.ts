import type { FastifyInstance } from 'fastify';
import type { ProjectSessions } from '../projects/sessions.js';
import type { UpdatePackageOptions, UpdatePackagePlan, UpdatePlanInput, UpdatePackageBuildInput, UpdatePackageArtifact } from '../../../../shared/update-packages.js';
import { ProjectError } from '../projects/store.js';
import { developmentHost } from './host.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id'], properties: { id: identity } };
const revision = { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER };
const metadata = { type: 'object', additionalProperties: false,
  required: ['packageId', 'packageVersion', 'targetRelease', 'title', 'description'],
  properties: { packageId: { type: 'string', minLength: 1, maxLength: 48 },
    packageVersion: { type: 'string', maxLength: 24 }, targetRelease: { type: 'string', maxLength: 24 },
    title: { type: 'string', minLength: 1, maxLength: 96 }, description: { type: 'string', minLength: 1, maxLength: 2048 } } };
const requirement = { type: 'object', additionalProperties: false,
  required: ['kind', 'name', 'target', 'minVersion', 'state'],
  properties: { kind: { type: 'string', enum: ['KERNEL', 'R4X', 'R4L', 'R4D', 'R4P'] },
    name: { type: 'string', minLength: 1, maxLength: 48 }, target: { type: 'string', minLength: 1, maxLength: 1023 },
    minVersion: { type: 'string', minLength: 1, maxLength: 24 }, state: { type: 'string', enum: ['installed', 'active'] } } };
export function updatePackageRoutes(app: FastifyInstance, security: ProjectSessions) {
  const base = '/:id/update-packages';

  app.get<{ Params: { id: string } }>(base + '/installations', { schema: { params } }, async (request, reply) => {
    security.session(request, reply); return developmentHost({ operation: 'update_list', projectId: request.params.id });
  });
  app.get<{ Params: { id: string; updateId: string } }>(base + '/installations/:updateId', {
    schema: { params: { ...params, required: ['id', 'updateId'], properties: { id: identity, updateId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply); return developmentHost({ operation: 'read_update', projectId: request.params.id, id: request.params.updateId });
  });
  for (const [route, operation, properties] of [
    ['installs', 'update_install', { transferJobIds: { type: 'array', minItems: 1, maxItems: 16, uniqueItems: true, items: identity } }],
    ['recovery', 'update_recovery', { updateId: identity, updateRevision: revision, vmRevision: { type: 'string', minLength: 1, maxLength: 100 },
      targetRelease: { type: 'string', maxLength: 24 }, action: { type: 'string', enum: ['resume', 'resume-batch', 'abort-batch', 'rollback-last', 'cleanup'] }, confirmReboot: { type: 'boolean' } }],
    ['verifications', 'update_verify', { updateId: identity, updateRevision: revision,
      deadlineSeconds: { type: 'integer', minimum: 30, maximum: 300 }, fullArtifactHashes: { type: 'boolean' } }],
    ['commits', 'update_commit', { updateId: identity, updateRevision: revision, batchId: { type: 'string', pattern: '^[0-9]{1,20}$' },
      targetRelease: { type: 'string', maxLength: 24 }, vmRevision: { type: 'string', minLength: 1, maxLength: 100 }, confirmReboot: { type: 'boolean', const: true } }],
  ] as const) {
    const fields = { requestId: identity, projectRevision: revision, ...properties };
    app.post<{ Params: { id: string }; Body: Record<string, unknown> }>(base + '/' + route, {
      bodyLimit: 8192,
      preValidation: async request => {
        if (!request.body || typeof request.body !== 'object' || Object.keys(request.body).some(key => !Object.hasOwn(fields, key))) {
          throw new ProjectError('Unexpected native update action fields.', 400);
        }
      },
      schema: { params, body: { type: 'object', additionalProperties: false, required: Object.keys(fields), properties: fields } },
    }, async (request, reply) => {
      security.mutation(request, reply);
      return reply.code(202).send({ job: await developmentHost({ operation, projectId: request.params.id, input: request.body }) });
    });
  }
  for (const [route, operation] of [['probes', 'update_probe'], ['transfers', 'update_transfer']] as const) {
  app.post<{ Params: { id: string }; Body: { requestId: string; projectRevision: number; packageArtifactId: string } }>(base + '/' + route, {
    bodyLimit: 4096,
    preValidation: async request => {
      if (!request.body || typeof request.body !== 'object' || Object.keys(request.body).some(key =>
        !['requestId', 'projectRevision', 'packageArtifactId'].includes(key))) {
        throw new ProjectError('Unexpected update preflight fields.', 400);
      }
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'projectRevision', 'packageArtifactId'],
      properties: { requestId: identity, projectRevision: revision, packageArtifactId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return reply.code(202).send({ job: await developmentHost({ operation, projectId: request.params.id, input: request.body }) });
  });
  }
  app.post<{ Params: { id: string }; Body: UpdatePackageBuildInput }>(base + '/builds', {
    bodyLimit: 4096,
    preValidation: async request => {
      if (!request.body || typeof request.body !== 'object' || Object.keys(request.body).some(key =>
        !['requestId', 'projectRevision', 'planId', 'planSha256'].includes(key))) {
        throw new ProjectError('Unexpected package build fields.', 400);
      }
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'projectRevision', 'planId', 'planSha256'],
      properties: { requestId: identity, projectRevision: revision, planId: identity,
        planSha256: { type: 'string', pattern: '^[a-f0-9]{64}$' } } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return reply.code(202).send({ job: await developmentHost({ operation: 'package', projectId: request.params.id, input: request.body }) });
  });
  app.get<{ Params: { id: string; artifactId: string } }>(base + '/artifacts/:artifactId', {
    schema: { params: { ...params, required: ['id', 'artifactId'], properties: { id: identity, artifactId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return developmentHost<{ artifact: UpdatePackageArtifact }>({ operation: 'package_artifact', projectId: request.params.id, id: request.params.artifactId });
  });
  app.get<{ Params: { id: string } }>(base, { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return developmentHost<UpdatePackageOptions>({ operation: 'update_options', projectId: request.params.id });
  });
  app.post<{ Params: { id: string }; Body: UpdatePlanInput }>(base + '/plans', {
    bodyLimit: 65536,
    preValidation: async (request) => {
      const value = request.body;
      if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key =>
        !['requestId', 'projectRevision', 'configurationRevision', 'metadata', 'artifactIds', 'requirements'].includes(key))) {
        throw new ProjectError('Unexpected update package fields.', 400);
      }
      if ((value.metadata && typeof value.metadata === 'object' && Object.keys(value.metadata).some(key =>
        !['packageId', 'packageVersion', 'targetRelease', 'title', 'description'].includes(key))) ||
        (Array.isArray(value.requirements) && value.requirements.some(item => item && typeof item === 'object' &&
          Object.keys(item).some(key => !['kind', 'name', 'target', 'minVersion', 'state'].includes(key))))) {
        throw new ProjectError('Unexpected update metadata or requirement fields.', 400);
      }
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'projectRevision', 'configurationRevision', 'metadata', 'artifactIds', 'requirements'],
      properties: { requestId: identity, projectRevision: revision, configurationRevision: revision, metadata,
        artifactIds: { type: 'array', minItems: 1, maxItems: 32, uniqueItems: true, items: identity },
        requirements: { type: 'array', maxItems: 32, items: requirement } } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return reply.code(201).send(await developmentHost<{ plan: UpdatePackagePlan }>({
      operation: 'update_plan', projectId: request.params.id, input: request.body,
    }));
  });
  app.get<{ Params: { id: string; planId: string } }>(base + '/plans/:planId', {
    schema: { params: { ...params, required: ['id', 'planId'], properties: { id: identity, planId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return developmentHost<{ plan: UpdatePackagePlan }>({ operation: 'read_update_plan', projectId: request.params.id, id: request.params.planId });
  });
  app.post<{ Params: { id: string }; Body: { planIds: string[] } }>(base + '/batch-preview', {
    bodyLimit: 4096, schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['planIds'], properties: { planIds: { type: 'array', minItems: 1, maxItems: 16, uniqueItems: true, items: identity } } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return developmentHost({ operation: 'update_batch_preview', projectId: request.params.id, input: request.body });
  });
}
