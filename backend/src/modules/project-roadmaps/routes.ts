import type { FastifyInstance } from 'fastify';
import type { RoadmapMutation, RoadmapTarget } from '../../../../shared/project-roadmaps.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { roadmapStore } from './store.js';
import { ProjectError } from '../projects/store.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const pageQuery = { type: 'object', additionalProperties: false, properties: {
  cursor: { type: 'string', maxLength: 1024 }, limit: { type: 'integer', minimum: 1, maximum: 20 },
} };
type Params = { id: string; versionId: string; subversionId: string; itemId: string };
type Query = { cursor?: string; limit?: number };
const base = '/:id/roadmap';

function strictMutation(value: RoadmapMutation) {
  const exact = (object: unknown, allowed: string[]) => {
    if (!object || typeof object !== 'object' || Array.isArray(object)
      || Object.keys(object).some((key) => !allowed.includes(key))) throw new ProjectError('Unexpected roadmap fields.', 400);
  };
  exact(value, ['requestId', 'expectedRevision', 'currentVersionId', 'target', 'action', 'input']);
  if (!Number.isSafeInteger(value.expectedRevision)) throw new ProjectError('Invalid roadmap revision.', 400);
  exact(value.target, ['kind', 'id', 'versionId', 'subversionId']);
  const reference = value.target as unknown as Record<string, unknown>;
  for (const field of ['requestId', 'currentVersionId', 'action'] as const) {
    if (typeof value[field] !== 'string') throw new ProjectError('Invalid roadmap input.', 400);
  }
  for (const field of ['kind', 'id', 'versionId', 'subversionId'] as const) {
    if (Object.hasOwn(reference, field) && typeof reference[field] !== 'string') throw new ProjectError('Invalid roadmap target.', 400);
  }
  if (value.input !== undefined) {
    exact(value.input, ['number', 'title', 'description', 'vision', 'notes', 'status', 'ids', 'confirm']);
    for (const field of ['number', 'title', 'description', 'vision', 'notes', 'status'] as const) {
      if (Object.hasOwn(value.input, field) && typeof value.input[field] !== 'string') throw new ProjectError('Invalid roadmap text.', 400);
    }
    if (value.input.ids !== undefined && (!Array.isArray(value.input.ids) || value.input.ids.some((id) => typeof id !== 'string'))) {
      throw new ProjectError('Invalid roadmap order.', 400);
    }
  }
}

export function roadmapRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  const parameterSchema = (path: string) => {
    const names = [...path.matchAll(/:([a-zA-Z]+)/g)].map((match) => match[1]);
    return { type: 'object', required: names, properties: Object.fromEntries(names.map((name) => [name, uuid])) };
  };
  app.get<{ Params: Params; Querystring: Query }>(base, {
    schema: { params: parameterSchema(base), querystring: pageQuery },
  }, async (request, reply) => {
    sessions.session(request, reply);
    return roadmapStore(directory, { operation: 'overview', projectId: request.params.id, ...request.query });
  });
  app.post<{ Params: Params; Body: { requestId: string } }>(base + '/initialize', {
    bodyLimit: 4096,
    preValidation: async (request) => {
      const body = request.body;
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length !== 1
        || typeof body.requestId !== 'string') throw new ProjectError('Use a request ID to initialize the roadmap.', 400);
    },
    schema: { params: parameterSchema(base), body: { type: 'object', additionalProperties: false,
      required: ['requestId'], properties: { requestId: uuid } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return roadmapStore(directory, { operation: 'initialize', projectId: request.params.id, requestId: request.body.requestId });
  });
  app.get<{ Params: Params }>(base + '/current', { schema: { params: parameterSchema(base) } }, async (request, reply) => {
    sessions.session(request, reply);
    return roadmapStore(directory, { operation: 'current', projectId: request.params.id });
  });
  const targets: { path: string; reference: (params: Params) => RoadmapTarget }[] = [
    { path: '', reference: () => ({ kind: 'roadmap' }) },
    { path: '/versions/:versionId', reference: (p) => ({ kind: 'version', id: p.versionId }) },
    { path: '/versions/:versionId/subversions/:subversionId', reference: (p) => ({ kind: 'subversion', id: p.subversionId, versionId: p.versionId }) },
    ...(['tasks', 'acceptances'] as const).map((collection) => ({
      path: `/versions/:versionId/subversions/:subversionId/${collection}/:itemId`,
      reference: (p: Params): RoadmapTarget => ({ kind: collection === 'tasks' ? 'task' : 'acceptance', id: p.itemId, versionId: p.versionId, subversionId: p.subversionId }),
    })),
  ];
  for (const target of targets) {
    const path = base + target.path;
    const load = async (params: Params, operation: 'get' | 'notes') => {
      const reference = target.reference(params);
      if (reference.kind === 'roadmap') {
        const state = await roadmapStore<{ exists: boolean; roadmap?: { id: string } }>(directory, { operation: 'overview', projectId: params.id });
        if (state.roadmap) reference.id = state.roadmap.id;
      }
      return roadmapStore(directory, { operation, projectId: params.id, target: reference });
    };
    if (target.path) app.get<{ Params: Params }>(path, { schema: { params: parameterSchema(path) } }, async (request, reply) => {
      sessions.session(request, reply);
      return load(request.params, 'get');
    });
    app.get<{ Params: Params }>(path + '/notes', { schema: { params: parameterSchema(path) } }, async (request, reply) => {
      sessions.session(request, reply);
      return load(request.params, 'notes');
    });
  }
  for (const collection of ['versions', 'subversions', 'tasks', 'acceptances']) {
    const prefix = collection === 'versions' ? '' : '/versions/:versionId' + (collection === 'subversions' ? '' : '/subversions/:subversionId');
    const path = base + prefix + '/' + collection;
    app.get<{ Params: Params; Querystring: Query }>(path, {
      schema: { params: parameterSchema(path), querystring: pageQuery },
    }, async (request, reply) => {
      sessions.session(request, reply);
      return roadmapStore(directory, { operation: 'list', projectId: request.params.id, collection,
        ...(request.params.versionId ? { versionId: request.params.versionId } : {}),
        ...(request.params.subversionId ? { subversionId: request.params.subversionId } : {}), ...request.query });
    });
  }
  app.post<{ Params: Params; Body: RoadmapMutation }>(base + '/mutations', {
    bodyLimit: 131072,
    preValidation: async (request) => strictMutation(request.body),
    schema: { params: parameterSchema(base), body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'expectedRevision', 'currentVersionId', 'target', 'action'], properties: {
        requestId: uuid, expectedRevision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, currentVersionId: uuid,
        target: { type: 'object', additionalProperties: false, required: ['kind'], properties: {
          kind: { enum: ['roadmap', 'version', 'subversion', 'task', 'acceptance'] }, id: uuid, versionId: uuid, subversionId: uuid,
        } },
        action: { enum: ['create', 'update', 'append_notes', 'replace_notes', 'reorder', 'delete', 'set_current'] },
        input: { type: 'object', additionalProperties: false, properties: {
          number: { type: 'string', maxLength: 35 }, title: { type: 'string', maxLength: 240 },
          description: { type: 'string', maxLength: 32768 }, vision: { type: 'string', maxLength: 32768 }, notes: { type: 'string', maxLength: 32768 },
          status: { enum: ['open', 'complete', 'discarded', 'done'] }, confirm: { const: true },
          ids: { type: 'array', maxItems: 500, uniqueItems: true, items: uuid },
        } },
      } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return roadmapStore(directory, { operation: 'mutate', projectId: request.params.id, input: request.body });
  });
}
