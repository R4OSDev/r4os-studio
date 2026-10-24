import type { FastifyInstance } from 'fastify';
import type { AgentEvent, AgentRun, AgentSession } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
type Params = { id: string; sessionId: string };
type EventResponse = { events: AgentEvent[]; session: AgentSession };

export function runRoutes(app: FastifyInstance, security: ProjectSessions) {
  const base = '/:id/sessions/:sessionId';
  const streams = new Set<() => void>();
  app.addHook('preClose', async () => { for (const close of streams) close(); });
  app.get('/agent-capabilities', async (request, reply) => {
    security.session(request, reply);
    try { return await agentHost({ operation: 'capabilities' }); }
    catch { return { enabled: false, protocol: 1, message: 'Agent host support is unavailable.' }; }
  });
  app.post<{ Params: Params; Body: { requestId: string; revision: number; text: string } }>(base + '/runs', {
    bodyLimit: 72 * 1024, schema: { params, body: { type: 'object', additionalProperties: false,
      required: ['requestId', 'revision', 'text'], properties: { requestId: identity,
        revision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, text: { type: 'string', minLength: 1, maxLength: 65536 } } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    const support = await agentHost<{ projectInstructions?: number; vmStartTools?: number }>({ operation: 'capabilities' });
    if (support.projectInstructions !== 1 || support.vmStartTools !== 1) throw new ProjectError('The agent coordinator must adopt this Studio release before starting a new run.', 503);
    const run = await agentHost<AgentRun>({ operation: 'start_run', projectId: request.params.id, sessionId: request.params.sessionId,
      input: { ...request.body, projectInstructions: 1 } });
    return reply.code(202).send({ run });
  });
  app.post<{ Params: Params & { runId: string } }>(base + '/runs/:runId/stop', {
    schema: { params: { ...params, required: ['id', 'sessionId', 'runId'], properties: { ...params.properties, runId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return { run: await agentHost<AgentRun>({ operation: 'stop_run', projectId: request.params.id, sessionId: request.params.sessionId, runId: request.params.runId }) };
  });
  app.get<{ Params: Params; Querystring: { after?: number } }>(base + '/events', {
    schema: { params, querystring: { type: 'object', additionalProperties: false, properties: { after: { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER } } } },
  }, async (request, reply) => {
    security.session(request, reply);
    if (streams.size >= 32) throw new ProjectError('Too many open session streams.', 429);
    let after = request.query.after ?? 0;
    const last = request.headers['last-event-id'];
    if (typeof last === 'string' && /^\d{1,16}$/.test(last) && Number.isSafeInteger(Number(last))) after = Math.max(after, Number(last));
    const payload = { operation: 'events', projectId: request.params.id, sessionId: request.params.sessionId };
    // Validate session/project ownership before committing an HTTP stream.
    const initial = await agentHost<EventResponse>({ ...payload, after });
    reply.hijack();
    const response = reply.raw;
    response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
    response.flushHeaders();
    let closed = false, timer: NodeJS.Timeout | undefined;
    const close = () => { closed = true; clearTimeout(timer); streams.delete(close); response.end(); };
    streams.add(close);
    response.on('close', () => { closed = true; clearTimeout(timer); streams.delete(close); });
    const send = (result: EventResponse) => {
      for (const event of result.events) {
        if (event.seq <= after) continue;
        const frame = `id: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`;
        after = event.seq;
        if (!response.write(frame) || response.writableLength > 512 * 1024) { close(); break; }
      }
    };
    send(initial);
    let heartbeats = 0;
    const poll = async () => {
      if (closed) return;
      try {
        send(await agentHost<EventResponse>({ ...payload, after }));
        if (++heartbeats % 40 === 0) response.write(': heartbeat\n\n');
        // Refresh authentication on bounded reconnects, without stopping a run.
        if (heartbeats >= 800) { close(); return; }
      } catch { close(); return; }
      if (!closed) timer = setTimeout(() => { void poll(); }, 300);
    };
    timer = setTimeout(() => { void poll(); }, 300);

  });
}
