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
    create_card: ['columnId', 'title', 'description'], update_card: ['cardId', 'expectedCardRevision', 'title', 'description', 'priority', 'dueDate', 'labelIds', 'checklist'], delete_card: ['cardId', 'expectedCardRevision', 'confirm'],
    create_label: ['name', 'color'], update_label: ['labelId', 'expectedLabelRevision', 'name', 'color'], delete_label: ['labelId', 'expectedLabelRevision', 'confirm'],
    move_card: ['cardId', 'expectedCardRevision', 'sourceColumnId', 'targetColumnId', 'position'], move_column: ['columnId', 'expectedColumnRevision', 'position'],
  };
  if (!Object.hasOwn(allowed, value.action) || !value.input || typeof value.input !== 'object' || Array.isArray(value.input)
    || Object.keys(value.input).some(key => !allowed[value.action].includes(key))) throw new ProjectError('Unexpected Board entry fields.', 400);
  const input = value.input;
  for (const key of ['title', 'description', 'cardId', 'columnId', 'sourceColumnId', 'targetColumnId', 'labelId', 'name', 'color', 'priority'] as const)
    if (Object.hasOwn(input, key) && typeof input[key] !== 'string') throw new ProjectError('Invalid Board entry text or identity.', 400);
  for (const key of ['expectedCardRevision', 'expectedColumnRevision', 'expectedLabelRevision'] as const)
    if (Object.hasOwn(input, key) && !Number.isSafeInteger(input[key])) throw new ProjectError('Invalid Board entry revision.', 400);
  if (Object.hasOwn(input, 'dueDate') && input.dueDate !== null && typeof input.dueDate !== 'string') throw new ProjectError('Invalid calendar date.', 400);
  if (Object.hasOwn(input, 'labelIds') && (!Array.isArray(input.labelIds) || input.labelIds.some(id => typeof id !== 'string'))) throw new ProjectError('Invalid card labels.', 400);
  if (Object.hasOwn(input, 'checklist') && (!Array.isArray(input.checklist) || input.checklist.some(item => !item || typeof item !== 'object' || Array.isArray(item)
    || Object.keys(item).some(key => !['id', 'text', 'checked', 'revision'].includes(key)) || typeof item.id !== 'string' || typeof item.text !== 'string' || typeof item.checked !== 'boolean' || !Number.isSafeInteger(item.revision)))) throw new ProjectError('Invalid checklist.', 400);
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
  app.get<{ Params: Params; Querystring: Query & { q: string } }>(base + '/:boardId/search', {
    schema: { params: parameterSchema(['id', 'boardId']), querystring: { ...querystring, required: ['q'], properties: { ...querystring.properties, q: { type: 'string', maxLength: 256 } } } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.session(request, reply);
    return boardStore(directory, { operation: 'search', projectId: request.params.id, boardId: request.params.boardId, clientLevel: request.query.clientLevel ?? 1, query: request.query.q });
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
        requestId: uuid, expectedRevision: revision, expectedOrderRevision: { ...revision, minimum: 1 }, action: { enum: ['create_column', 'update_column', 'delete_column', 'create_card', 'update_card', 'delete_card', 'move_card', 'move_column', 'create_label', 'update_label', 'delete_label'] },
        input: { type: 'object', additionalProperties: false, properties: {
          columnId: uuid, sourceColumnId: uuid, targetColumnId: uuid, cardId: uuid, expectedColumnRevision: { ...revision, minimum: 1 }, expectedCardRevision: { ...revision, minimum: 1 }, position: { type: 'integer', minimum: 0, maximum: 1000 },
          priority: { enum: ['low', 'normal', 'high'] }, dueDate: { anyOf: [{ type: 'string', pattern: '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' }, { type: 'null' }] },
          labelIds: { type: 'array', maxItems: 64, uniqueItems: true, items: uuid }, labelId: uuid, expectedLabelRevision: { ...revision, minimum: 1 }, name: { type: 'string', maxLength: 64 }, color: { enum: ['purple', 'blue', 'green', 'yellow', 'orange', 'pink', 'gray'] },
          checklist: { type: 'array', maxItems: 100, items: { type: 'object', additionalProperties: false, required: ['id', 'text', 'checked', 'revision'], properties: { id: uuid, text: { type: 'string', minLength: 1, maxLength: 240 }, checked: { type: 'boolean' }, revision } } },
          title: { type: 'string', maxLength: 240 }, description: { type: 'string', maxLength: 16000 }, confirm: { const: true },
        } },
      } } },
  }, async (request, reply) => {
    sessions.validate(request, reply); sessions.mutation(request, reply);
    return boardStore(directory, { operation: 'mutate', projectId: request.params.id, clientLevel: request.query.clientLevel ?? 1, boardId: request.params.boardId, input: request.body });
  });
}
