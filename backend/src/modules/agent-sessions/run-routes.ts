import type { FastifyInstance } from 'fastify';
import type { AgentEvent, AgentRun, AgentSession } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';
import { goalRoutes } from './goal-routes.js';
import { messageRoutes } from './message-routes.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
type Params = { id: string; sessionId: string };
type EventResponse = { events: AgentEvent[]; session: AgentSession };

export function runRoutes(app: FastifyInstance, security: ProjectSessions, ownerType: 'project' | 'skill' = 'project') {
  goalRoutes(app, security, ownerType);
  messageRoutes(app, security, ownerType);
  const base = '/:id/sessions/:sessionId';
  const owner = (id: string) => ownerType === 'skill' ? { ownerType, ownerId: id } : { projectId: id };
  const streams = new Set<() => void>();
  app.addHook('preClose', async () => { for (const close of streams) close(); });
  app.get('/agent-capabilities', async (request, reply) => {
    security.session(request, reply);
    try { return await agentHost({ operation: 'capabilities' }); }
    catch { return { enabled: false, protocol: 1, message: 'Agent host support is unavailable.' }; }
  });
  app.get<{ Params: Params & { requestId: string } }>(base + '/runs/requests/:requestId', {
    schema: { params: { ...params, required: [...params.required, 'requestId'], properties: { ...params.properties, requestId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply); reply.header('Cache-Control', 'private, no-store');
    return { run: await agentHost<AgentRun>({ operation: 'run_receipt', ...owner(request.params.id), sessionId: request.params.sessionId, requestId: request.params.requestId }) };
  });
  app.post<{ Params: Params; Body: { requestId: string; revision: number; text: string; attachments?: string[] } }>(base + '/runs', {
    bodyLimit: 72 * 1024, schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'revision', 'text'], properties: { requestId: identity,
        revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, text: { type: 'string', maxLength: 65536 },
        attachments: { type: 'array', maxItems: 8, uniqueItems: true, items: identity } } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const support = await agentHost<{ environmentNotesSettings?: number; liveGoalPreparation?: number; imageGenerationSettings?: number; documentInputs?: number; nativeImageInputs?: number; remoteHostTools?: number; roadmapTools?: number; roadmapSettings?: number; nativeWebSearch?: number; projectInstructions?: number; vmStartTools?: number; skillSessions?: number; skillAuthorTools?: number; globalSkills?: number; skillScripts?: number }>({ operation: 'capabilities' });
    if (support.environmentNotesSettings !== 1 || support.liveGoalPreparation !== 1 || support.imageGenerationSettings !== 1 || support.documentInputs !== 1 || support.nativeImageInputs !== 1 || support.nativeWebSearch !== 1 || support.globalSkills !== 1 || support.skillScripts !== 1 || (ownerType === 'skill' ? (support.skillSessions !== 1 || support.skillAuthorTools !== 1) : (support.projectInstructions !== 1 || support.vmStartTools !== 1 || support.roadmapSettings !== 1 || support.roadmapTools !== 1 || support.remoteHostTools !== 1))) throw new ProjectError('The agent coordinator must adopt this Studio release before starting a new run.', 503);
    const run = await agentHost<AgentRun>({ operation: 'start_run', ...owner(request.params.id), sessionId: request.params.sessionId,
      input: { ...request.body, nativeWebSearch: 1, skillSelection: 1, skillScripts: 1, nativeImageInputs: 1, documentInputs: 1, environmentNotesSettings: 1, imageGenerationSettings: 1, liveGoalPreparation: 1, ...(ownerType === 'project' ? { projectInstructions: 1, roadmapSettings: 1, remoteHostTools: 1 } : {}) } });
    return reply.code(202).send({ run });
  });
  app.post<{ Params: Params & { runId: string } }>(base + '/runs/:runId/stop', {
    schema: { params: { ...params, required: ['id', 'sessionId', 'runId'], properties: { ...params.properties, runId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return { run: await agentHost<AgentRun>({ operation: 'stop_run', ...owner(request.params.id), sessionId: request.params.sessionId, runId: request.params.runId }) };
  });
  app.get<{ Params: Params; Querystring: { after?: number } }>(base + '/events', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: { after: { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER } } } },
  }, async (request, reply) => {
    security.session(request, reply);
    if (streams.size >= 32) throw new ProjectError('Too many open session streams.', 429);
    let after = request.query.after ?? 0;
    const last = request.headers['last-event-id'];
    if (typeof last === 'string' && /^\d{1,16}$/.test(last) && Number.isSafeInteger(Number(last))) after = Math.max(after, Number(last));
    const payload = { operation: 'events', ...owner(request.params.id), sessionId: request.params.sessionId };
    // Validate session/project ownership before committing an HTTP stream.
    const initial = await agentHost<EventResponse>({ ...payload, after });
    reply.hijack();
    const response = reply.raw;
    let closed = false, timer: NodeJS.Timeout | undefined;
    const release = () => { closed = true; clearTimeout(timer); streams.delete(close); };
    const close = () => {
      if (closed) return;
      release();
      if (!response.writableEnded && !response.destroyed) response.end();
    };
    const writable = () => {
      if (closed) return false;
      if (response.writableEnded || response.destroyed) { release(); return false; }
      return true;
    };
    const write = (frame: string) => {
      if (!writable()) return false;
      if (!response.write(frame) || response.writableLength > 512 * 1024) { close(); return false; }
      return true;
    };
    streams.add(close);
    response.on('close', release);
    response.on('finish', release);
    // ServerResponse errors are emitted asynchronously, outside poll's catch.
    response.on('error', close);
    let caughtUp=false;
    const send = (result: EventResponse) => {
      if (!writable()) return false;
      for (const event of result.events) {
        if (event.seq <= after) continue;
        const frame = `id: ${event.seq}\ndata: ${JSON.stringify({...event,delivery:caughtUp?'live':'replay'})}\n\n`;
        after = event.seq;
        if (!write(frame)) return false;
      }
      if(!result.events.length)caughtUp=true;
      return writable();
    };
    try {
      if (!writable()) return;
      response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
      response.flushHeaders();
      if (!send(initial)) return;
    } catch { close(); return; }
    let heartbeats = 0;
    const poll = async () => {
      if (!writable()) return;
      try {
        // The response may close while the original read is in flight.
        if (!send(await agentHost<EventResponse>({ ...payload, after }))) return;
        if (++heartbeats % 40 === 0 && !write(': heartbeat\n\n')) return;
        // Refresh authentication on bounded reconnects, without stopping a run.
        if (heartbeats >= 800) { close(); return; }
      } catch { close(); return; }
      if (writable()) timer = setTimeout(() => { void poll(); }, 300);
    };
    timer = setTimeout(() => { void poll(); }, 300);

  });
}
