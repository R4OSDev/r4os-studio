import type { FastifyInstance } from 'fastify';
import type { BoardCreate, BoardMutation, BoardOrder, BoardUpdate } from '../../../../shared/project-boards.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { boardStore } from './store.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const revision = { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER };
const base = '/:id/boards';
type Query = { clientLevel?: number };
const querystring = { type: 'object', additionalProperties: false, properties: { clientLevel: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER } } };
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
function strictEntry(value: BoardMutation) {
  strict(value, ['requestId', 'expectedRevision', 'expectedOrderRevision', 'action', 'input']);
  if (Object.hasOwn(value, 'expectedOrderRevision') && !Number.isSafeInteger(value.expectedOrderRevision)) throw new ProjectError('Invalid Board order revision.', 400);
  const allowed = {
    create_column: ['title'], update_column: ['columnId', 'expectedColumnRevision', 'title'], delete_column: ['columnId', 'expectedColumnRevision', 'confirm', 'targetColumnId'],
    create_card: ['columnId', 'title', 'description'], update_card: ['cardId', 'expectedCardRevision', 'title', 'description'], delete_card: ['cardId', 'expectedCardRevision', 'confirm'],
    move_card: ['cardId', 'expectedCardRevision', 'sourceColumnId', 'targetColumnId', 'position'], move_column: ['columnId', 'expectedColumnRevision', 'position'],
  };
  if (!Object.hasOwn(allowed, value.action) || !value.input || typeof value.input !== 'object' || Array.isArray(value.input)
    || Object.keys(value.input).some(key => !allowed[value.action].includes(key))) throw new ProjectError('Unexpected Board entry fields.', 400);
  const input = value.input;
  for (const key of ['title', 'description', 'cardId', 'columnId', 'sourceColumnId', 'targetColumnId'] as const)
    if (Object.hasOwn(input, key) && typeof input[key] !== 'string') throw new ProjectError('Invalid Board entry text or identity.', 400);
  for (const key of ['expectedCardRevision', 'expectedColumnRevision'] as const)
    if (Object.hasOwn(input, key) && !Number.isSafeInteger(input[key])) throw new ProjectError('Invalid Board entry revision.', 400);
  if (Object.hasOwn(input, 'position') && !Number.isSafeInteger(input.position)) throw new ProjectError('Invalid Board entry position.', 400);
}

export function boardRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  type Params = { id: string; boardId: string; requestId: string; cardId: string };
  for (const [suffix, operation, names] of [
    ['', 'list', ['id']], ['/:boardId', 'get', ['id', 'boardId']], ['/receipts/:requestId', 'receipt', ['id', 'requestId']], ['/:boardId/cards/:cardId', 'card', ['id', 'boardId', 'cardId']],
  ] as const) app.get<{ Params: Params; Querystring: Query }>(base + suffix, { schema: { params: parameterSchema([...names]), querystring } }, async (request, reply) => {
    sessions.validate(request, reply); sessions.session(request, reply);
    return boardStore(directory, { operation, projectId: request.params.id, clientLevel: request.query.clientLevel ?? 1,
      ...(operation === 'get' || operation === 'card' ? { boardId: request.params.boardId } : {}), ...(operation === 'card' ? { cardId: request.params.cardId } : {}), ...(operation === 'receipt' ? { requestId: request.params.requestId } : {}) });
  });
  const properties = { requestId: uuid, expectedRevision: revision, name: { type: 'string', minLength: 1, maxLength: 120 }, description: { type: 'string', maxLength: 8000 } };
  app.post<{ Params: Params; Querystring: Query; Body: BoardCreate }>(base, {
    bodyLimit: 131072, preValidation: async request => strict(request.body, ['requestId', 'expectedRevision', 'name', 'description']),
    schema: { params: parameterSchema(['id']), querystring, body: { type: 'object', additionalProperties: false, required: ['requestId', 'expectedRevision', 'name'], properties } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'create', projectId: request.params.id, clientLevel: request.query.clientLevel ?? 1, input: request.body });
  });
  app.patch<{ Params: Params; Querystring: Query; Body: BoardUpdate }>(base + '/:boardId', {
    bodyLimit: 131072, preValidation: async request => strict(request.body, ['requestId', 'expectedRevision', 'name', 'description']),
    schema: { params: parameterSchema(['id', 'boardId']), querystring, body: { type: 'object', additionalProperties: false, required: ['requestId', 'expectedRevision'], properties } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'update', projectId: request.params.id, clientLevel: request.query.clientLevel ?? 1, boardId: request.params.boardId, input: request.body });
  });
  app.post<{ Params: Params; Querystring: Query; Body: BoardOrder }>(base + '/order', {
    bodyLimit: 8192, preValidation: async request => strict(request.body, ['requestId', 'expectedRevision', 'ids']),
    schema: { params: parameterSchema(['id']), querystring, body: { type: 'object', additionalProperties: false, required: ['requestId', 'expectedRevision', 'ids'], properties: {
      requestId: uuid, expectedRevision: revision, ids: { type: 'array', maxItems: 100, uniqueItems: true, items: uuid },
    } } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'reorder', projectId: request.params.id, clientLevel: request.query.clientLevel ?? 1, input: request.body });
  });
  app.post<{ Params: Params; Querystring: Query; Body: BoardMutation }>(base + '/:boardId/mutations', {
    bodyLimit: 131072, preValidation: async request => strictEntry(request.body),
    schema: { params: parameterSchema(['id', 'boardId']), querystring, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'expectedRevision', 'action', 'input'], properties: {
        requestId: uuid, expectedRevision: revision, expectedOrderRevision: { ...revision, minimum: 1 }, action: { enum: ['create_column', 'update_column', 'delete_column', 'create_card', 'update_card', 'delete_card', 'move_card', 'move_column'] },
        input: { type: 'object', additionalProperties: false, properties: {
          columnId: uuid, sourceColumnId: uuid, targetColumnId: uuid, cardId: uuid, expectedColumnRevision: { ...revision, minimum: 1 }, expectedCardRevision: { ...revision, minimum: 1 }, position: { type: 'integer', minimum: 0, maximum: 1000 },
          title: { type: 'string', maxLength: 240 }, description: { type: 'string', maxLength: 16000 }, confirm: { const: true },
        } },
      } } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'mutate', projectId: request.params.id, clientLevel: request.query.clientLevel ?? 1, boardId: request.params.boardId, input: request.body });
  });
}
