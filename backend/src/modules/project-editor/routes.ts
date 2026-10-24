import type { FastifyInstance } from 'fastify';
import type { ProjectSessions } from '../projects/sessions.js';
import { projectStore, ProjectError } from '../projects/store.js';
import { maintenanceHosts } from '../projects/maintenance.js';
import type { EditorMutation } from '../../../../shared/project-editor.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const path = { type: 'string', maxLength: 1024 };
const params = { type: 'object', required: ['id'], properties: { id: identity } };
export function editorRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  app.post<{ Params: { id: string }; Body: EditorMutation }>('/:id/editor/mutations', {
    bodyLimit: 2 * 1024 * 1024,
    preValidation: async (request) => {
      if (request.body && Object.keys(request.body).some((key) => !['requestId', 'kind', 'path', 'target', 'expected', 'text', 'format', 'confirm'].includes(key)))
        throw new ProjectError('Unexpected editor mutation fields.', 400);
    },
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'kind', 'path'], properties: {
      requestId: identity, kind: { enum: ['save', 'create', 'mkdir', 'rename', 'delete'] }, path, target: path,
      expected: { type: 'object', additionalProperties: false, required: ['revision'], properties: {
        revision: { type: 'string', pattern: '^[a-f0-9]{64}$' }, sha256: { type: 'string', pattern: '^[a-f0-9]{64}$' },
      } }, text: { type: 'string', maxLength: 524288 }, confirm: { const: true },
      format: { type: 'object', additionalProperties: false, required: ['bom', 'eol'], properties: { bom: { type: 'boolean' }, eol: { enum: ['lf', 'crlf'] } } },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return projectStore(directory, { operation: 'mutation', id: request.params.id, input: request.body, hosts: await maintenanceHosts() }, 'editor');
  });
  app.get<{ Params: { id: string; requestId: string } }>('/:id/editor/operations/:requestId', {
    schema: { params: { type: 'object', required: ['id', 'requestId'], properties: { id: identity, requestId: identity } } },
  }, async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'receipt', id: request.params.id, input: { requestId: request.params.requestId } }, 'editor');
  });
  app.get<{ Params: { id: string }; Querystring: { path?: string; offset?: number; revision?: string } }>('/:id/editor/tree', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: {
      path, offset: { type: 'integer', minimum: 0, maximum: 10000 }, revision: { type: 'string', pattern: '^[a-f0-9]{64}$' },
    } } },
  }, async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'tree', id: request.params.id, input: request.query }, 'editor');
  });
  app.get<{ Params: { id: string }; Querystring: { path: string } }>('/:id/editor/file', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, required: ['path'], properties: { path } } },
  }, async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'file', id: request.params.id, input: request.query }, 'editor');
  });
  app.post<{ Params: { id: string }; Body: { paths: string[] } }>('/:id/editor/status', {
    bodyLimit: 32768,
    preValidation: async (request) => {
      if (request.body && Object.keys(request.body).some((key) => key !== 'paths')) throw new ProjectError('Unexpected editor fields.', 400);
    },
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['paths'], properties: {
      paths: { type: 'array', maxItems: 20, uniqueItems: true, items: path },
    } } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return projectStore(directory, { operation: 'status', id: request.params.id, input: request.body }, 'editor');
  });
}
