import type { FastifyInstance } from 'fastify';
import type { ProjectPinUpdate } from '../../../../shared/projects.js';
import type { ProjectSessions } from './sessions.js';
import { projectStore, ProjectError } from './store.js';
import { developmentHost } from '../project-development/host.js';
import { maintenanceHosts } from './maintenance.js';
import { agentHost } from '../agent-sessions/host.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id'], properties: { id: identity } };

export function projectPinRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  app.get<{ Params: { id: string } }>('/:id/pins', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'options', id: request.params.id }, 'project_pins');
  });
  app.get<{ Params: { id: string; requestId: string } }>('/:id/pins/requests/:requestId', {
    schema: { params: { ...params, required: ['id', 'requestId'], properties: { id: identity, requestId: identity } } },
  }, async (request, reply) => {
    sessions.session(request, reply);
    return projectStore(directory, { operation: 'receipt', ...request.params }, 'project_pins');
  });
  app.post<{ Params: { id: string }; Body: ProjectPinUpdate }>('/:id/pins', {
    bodyLimit: 4096,
    preValidation: async (request, reply) => {
      sessions.mutation(request, reply);
      if (!request.body || typeof request.body !== 'object' || Array.isArray(request.body)
        || Object.keys(request.body).some(key => !['requestId', 'revision', 'sdkId', 'selectionId'].includes(key))) {
        throw new ProjectError('Unexpected project pin fields.', 400);
      }
    },
    schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'revision', 'sdkId', 'selectionId'], properties: {
        requestId: identity, revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
        sdkId: { type: 'string', pattern: '^[a-f0-9]{40}$' }, selectionId: { type: 'string', pattern: '^[a-f0-9]{64}$' },
      } } },
  }, async request => {
    const capabilities = await developmentHost<{ enabled: boolean; features: { projectPins?: number } }>({ operation: 'capabilities' });
    if (!capabilities.enabled || capabilities.features.projectPins !== 1) throw new ProjectError('Update the development coordinator before changing project pins.', 503);
    const agents = await agentHost<{ projectPinLocks?: number }>({ operation: 'capabilities' });
    if (agents.projectPinLocks !== 1) throw new ProjectError('Wait for the agent coordinator update before changing project pins.', 503);
    return developmentHost({ operation: 'project_pins_apply', projectId: request.params.id, input: request.body, hosts: await maintenanceHosts() });
  });
}
