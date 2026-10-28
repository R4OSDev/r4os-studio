import type { FastifyInstance } from 'fastify';
import type { GoalCommand, GoalReceipt, SessionGoal } from '../../../../shared/agent-inputs.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
type Params = { id: string; sessionId: string };

export function goalRoutes(app: FastifyInstance, security: ProjectSessions, ownerType: 'project' | 'skill') {
  const base = '/:id/sessions/:sessionId/goal';
  const owner = (id: string) => ({ ownerType, ownerId: id });
  app.get<{ Params: Params }>(base, { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return { goal: await agentHost<SessionGoal>({ operation: 'goal', ...owner(request.params.id), sessionId: request.params.sessionId }) };
  });
  app.get<{ Params: Params }>(base + '/clock', { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return agentHost({ operation: 'goal_clock', ...owner(request.params.id), sessionId: request.params.sessionId });
  });
  app.post<{ Params: Params }>(base + '/readback', { bodyLimit: 1024, schema: { params,
    body: { type: 'object', additionalProperties: false, maxProperties: 0 } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const support = await agentHost<{ nativeGoalReadback?: number }>({ operation: 'capabilities' });
    if (support.nativeGoalReadback !== 1) throw new ProjectError('Native Goal readback is unavailable until current runs finish.', 503);
    return agentHost<{ goal: SessionGoal; nativeRead: boolean; superseded: boolean }>({ operation: 'goal_readback', ...owner(request.params.id), sessionId: request.params.sessionId });
  });
  app.get<{ Params: Params & { requestId: string } }>(base + '/requests/:requestId', {
    schema: { params: { ...params, required: ['id', 'sessionId', 'requestId'], properties: { ...params.properties, requestId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return { receipt: await agentHost<GoalReceipt>({ operation: 'goal_receipt', ...owner(request.params.id), sessionId: request.params.sessionId, requestId: request.params.requestId }) };
  });
  app.post<{ Params: Params; Body: GoalCommand }>(base, { bodyLimit: 24 * 1024,
    schema: { params, body: { type: 'object', additionalProperties: false, required: ['requestId', 'revision', 'action'], properties: {
      requestId: identity, revision: { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER },
      sessionRevision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER },
      target: { type: 'object', additionalProperties: false, required: ['runId','threadId','turnId'], properties: { runId: identity, threadId: { type: 'string', minLength: 1, maxLength: 256 }, turnId: { type: 'string', minLength: 1, maxLength: 256 } } },
      action: { type: 'string', enum: ['save', 'play', 'pause', 'stop'] }, objective: { type: 'string', maxLength: 16000 },
    } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const support = await agentHost<{ environmentNotesSettings?: number; liveGoalControl?: number; nativeGoals?: number; nativeGoalExecution?: number; nativeImageInputs?: number; documentInputs?: number; imageGenerationSettings?: number }>({ operation: 'capabilities' });
    if (request.body.target && support.liveGoalControl !== 1) throw new ProjectError('This coordinator cannot control a live Goal yet. Your draft was preserved.', 503);
    if (support.nativeGoals !== 1) throw new ProjectError('The agent coordinator must adopt Goal support first.', 503);
    if (request.body.action === 'play' && (support.environmentNotesSettings !== 1 || support.imageGenerationSettings !== 1 || support.nativeGoalExecution !== 2 || support.nativeImageInputs !== 1 || support.documentInputs !== 1))
      throw new ProjectError('Wait for current runs to finish before starting a Goal.', 503);
    const receipt = await agentHost<GoalReceipt>({ operation: 'goal_command', ...owner(request.params.id), sessionId: request.params.sessionId, input: request.body });
    return reply.code(receipt.state === 'pending' ? 202 : 200).send({ receipt });
  });
}
