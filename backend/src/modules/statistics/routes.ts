import type { FastifyInstance } from 'fastify';
import type { StatisticsSnapshot } from '../../../../shared/statistics.js';
import { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from '../agent-sessions/host.js';
export async function statisticsRoutes(app: FastifyInstance) {
  const security = new ProjectSessions('statistics');
  app.addHook('onRequest', async (request, reply) => security.validate(request, reply));
  app.get('/', async (request, reply) => {
    security.session(request, reply, true);
    return agentHost<StatisticsSnapshot>({ operation: 'statistics', scope: 'global' });
  });
}
export function scopedStatisticsRoutes(app: FastifyInstance, security: ProjectSessions, ownerType: 'project' | 'skill') {
  const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
  if (ownerType === 'project') app.get<{ Params: { id: string } }>('/:id/statistics', {
    schema: { params: { type: 'object', additionalProperties: false, required: ['id'], properties: { id: uuid } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return agentHost<StatisticsSnapshot>({ operation: 'statistics', scope: 'project', ownerType, ownerId: request.params.id });
  });
  app.get<{ Params: { id: string; sessionId: string } }>('/:id/sessions/:sessionId/statistics', {
    schema: { params: { type: 'object', additionalProperties: false, required: ['id','sessionId'], properties: { id: uuid, sessionId: uuid } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return agentHost<StatisticsSnapshot>({ operation: 'statistics', scope: 'session', ownerType, ownerId: request.params.id, sessionId: request.params.sessionId });
  });
}
