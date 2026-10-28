import type { FastifyInstance } from 'fastify';
import type { BoardCreate, BoardOrder, BoardUpdate } from '../../../../shared/project-boards.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { boardStore } from './store.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const revision = { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER };
const base = '/:id/boards';
const parameterSchema = (names: string[]) => ({ type: 'object', additionalProperties: false, required: names, properties: Object.fromEntries(names.map(name => [name, uuid])) });
function strict(value: unknown, allowed: string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key => !allowed.includes(key)))
    throw new ProjectError('Unexpected Board fields.', 400);
  const body = value as Record<string, unknown>;
  for (const key of ['requestId', 'name', 'description'])
    if (Object.hasOwn(body, key) && typeof body[key] !== 'string') throw new ProjectError('Invalid Board text.', 400);
  if (!Number.isSafeInteger(body.expectedRevision)) throw new ProjectError('Invalid Board revision.', 400);
  if (Object.hasOwn(body, 'ids') && (!Array.isArray(body.ids) || body.ids.some(id => typeof id !== 'string')))
    throw new ProjectError('Invalid Board order.', 400);
}

export function boardRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  type Params = { id: string; boardId: string; requestId: string };
  for (const [suffix, operation, names] of [
    ['', 'list', ['id']], ['/:boardId', 'get', ['id', 'boardId']], ['/receipts/:requestId', 'receipt', ['id', 'requestId']],
  ] as const) app.get<{ Params: Params }>(base + suffix, { schema: { params: parameterSchema([...names]) } }, async (request, reply) => {
    sessions.validate(request, reply); sessions.session(request, reply);
    return boardStore(directory, { operation, projectId: request.params.id,
      ...(operation === 'get' ? { boardId: request.params.boardId } : {}), ...(operation === 'receipt' ? { requestId: request.params.requestId } : {}) });
  });
  const properties = { requestId: uuid, expectedRevision: revision, name: { type: 'string', minLength: 1, maxLength: 120 }, description: { type: 'string', maxLength: 8000 } };
  app.post<{ Params: Params; Body: BoardCreate }>(base, {
    bodyLimit: 131072, preValidation: async request => strict(request.body, ['requestId', 'expectedRevision', 'name', 'description']),
    schema: { params: parameterSchema(['id']), body: { type: 'object', additionalProperties: false, required: ['requestId', 'expectedRevision', 'name'], properties } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'create', projectId: request.params.id, input: request.body });
  });
  app.patch<{ Params: Params; Body: BoardUpdate }>(base + '/:boardId', {
    bodyLimit: 131072, preValidation: async request => strict(request.body, ['requestId', 'expectedRevision', 'name', 'description']),
    schema: { params: parameterSchema(['id', 'boardId']), body: { type: 'object', additionalProperties: false, required: ['requestId', 'expectedRevision'], properties } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'update', projectId: request.params.id, boardId: request.params.boardId, input: request.body });
  });
  app.post<{ Params: Params; Body: BoardOrder }>(base + '/order', {
    bodyLimit: 8192, preValidation: async request => strict(request.body, ['requestId', 'expectedRevision', 'ids']),
    schema: { params: parameterSchema(['id']), body: { type: 'object', additionalProperties: false, required: ['requestId', 'expectedRevision', 'ids'], properties: {
      requestId: uuid, expectedRevision: revision, ids: { type: 'array', maxItems: 100, uniqueItems: true, items: uuid },
    } } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'reorder', projectId: request.params.id, input: request.body });
  });
}
