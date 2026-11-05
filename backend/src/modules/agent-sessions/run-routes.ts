import type { FastifyInstance } from 'fastify';
import type { AgentRun } from '../../../../shared/agent-sessions.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { agentHost } from './host.js';
import { ProjectError } from '../projects/store.js';
import { goalRoutes } from './goal-routes.js';
import { messageRoutes } from './message-routes.js';
import { SessionStreams, type EventPage } from './event-stream.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: { id: identity, sessionId: identity } };
type Params = { id: string; sessionId: string };

export function runRoutes(app: FastifyInstance, security: ProjectSessions, ownerType: 'project' | 'skill' = 'project') {
  goalRoutes(app, security, ownerType);
  messageRoutes(app, security, ownerType);
  const base = '/:id/sessions/:sessionId';
  const owner = (id: string) => ownerType === 'skill' ? { ownerType, ownerId: id } : { projectId: id };
  const streams = new Set<() => void>(), shared = new SessionStreams();
  const pendingStreams = new Set<() => void>();
  let preparing = 0;
  app.addHook('preClose', async () => { for (const close of [...streams, ...pendingStreams]) close(); });
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
    const support = await agentHost<{ environmentNotesSettings?: number; liveGoalPreparation?: number; imageGenerationSettings?: number; documentInputs?: number; nativeImageInputs?: number; remoteHostTools?: number; roadmapTools?: number; roadmapSettings?: number; nativeWebSearch?: number; projectInstructions?: number; vmStartTools?: number; skillSessions?: number; skillAuthorTools?: number; globalSkills?: number; skillMcp?: number; skillScripts?: number }>({ operation: 'capabilities' });
    if (support.environmentNotesSettings !== 1 || support.liveGoalPreparation !== 1 || support.imageGenerationSettings !== 1 || support.documentInputs !== 1 || support.nativeImageInputs !== 1 || support.nativeWebSearch !== 1 || support.globalSkills !== 1 || support.skillScripts !== 1 || support.skillMcp !== 1 || (ownerType === 'skill' ? (support.skillSessions !== 1 || support.skillAuthorTools !== 1) : (support.projectInstructions !== 1 || support.vmStartTools !== 1 || support.roadmapSettings !== 1 || support.roadmapTools !== 1 || support.remoteHostTools !== 1))) throw new ProjectError('The agent coordinator must adopt this Studio release before starting a new run.', 503);
    const run = await agentHost<AgentRun>({ operation: 'start_run', ...owner(request.params.id), sessionId: request.params.sessionId,
      input: { ...request.body, nativeWebSearch: 1, skillSelection: 1, skillScripts: 1, skillMcp: 1, nativeImageInputs: 1, documentInputs: 1, environmentNotesSettings: 1, imageGenerationSettings: 1, liveGoalPreparation: 1, ...(ownerType === 'project' ? { projectInstructions: 1, roadmapSettings: 1, remoteHostTools: 1 } : {}) } });
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
    if (streams.size + preparing >= 32) throw new ProjectError('Too many open session streams.', 429);
    let after = request.query.after ?? 0;
    const last = request.headers['last-event-id'];
    if (typeof last === 'string' && /^\d{1,16}$/.test(last) && Number.isSafeInteger(Number(last))) after = Math.max(after, Number(last));
    const payload = { operation: 'events', ...owner(request.params.id), sessionId: request.params.sessionId };
    const lease = shared.acquire(payload), response = reply.raw;
    let closed = false, released = false, started = false;
    let timer: NodeJS.Timeout | undefined, immediate: NodeJS.Immediate | undefined;
    const release = () => {
      if (released) return;
      closed = released = true; clearTimeout(timer); clearImmediate(immediate);
      streams.delete(close); lease.release();
    };
    const close = () => {
      if (closed) return;
      release();
      if (started && !response.writableEnded && !response.destroyed) response.end();
      else if (!started && !response.destroyed) response.destroy();
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
    response.on('close', release); response.on('finish', release); response.on('error', close);
    // Count pending validation too; simultaneous reconnects cannot exceed 32.
    preparing++;
    pendingStreams.add(close);
    let initial: EventPage;
    try { initial = await lease.reader.read(after); }
    catch (error) { release(); if (!response.destroyed) throw error; return; }
    finally { preparing--; pendingStreams.delete(close); }
    if (!writable()) return;
    security.session(request, reply);
    reply.hijack(); started = true; streams.add(close);
    const initialWatermark = initial.watermark;
    let caughtUp = initialWatermark !== undefined && after >= initialWatermark;
    const send = (result: EventPage) => {
      if (!writable()) return false;
      for (const event of result.events) {
        if (event.seq <= after) continue;
        const live = initialWatermark === undefined ? caughtUp : event.seq > initialWatermark;
        const frame = `id: ${event.seq}\ndata: ${JSON.stringify({...event,delivery:live?'live':'replay'})}\n\n`;
        after = event.seq;
        if (!write(frame)) return false;
      }
      if (initialWatermark === undefined ? !result.events.length : after >= initialWatermark) caughtUp = true;
      return writable();
    };
    try {
      response.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
      response.flushHeaders();
      if (!send(initial)) return;
    } catch { close(); return; }
    const openedAt = Date.now(); let heartbeatAt = openedAt;
    let target = initial.hasMore ? initial.watermark : undefined;
    const schedule = (page: EventPage, more: boolean) => {
      if (!writable()) return;
      if (more) immediate = setImmediate(() => { void poll(); });
      else timer = setTimeout(() => { void poll(); }, Math.max(0, page.nextPollAt - Date.now()));
    };
    const poll = async () => {
      if (!writable()) return;
      try {
        for (let step = 0; step < 4; step++) {
          const previous = after, result = await lease.reader.read(after, target);
          if (!send(result)) return;
          // Legacy hosts drain until an empty page; no-progress replies never spin.
          const more = result.hasMore && after > previous;
          if (more && target === undefined) target = result.watermark;
          if (!more) target = undefined;
          const now = Date.now();
          if (now - openedAt >= 240_000) { close(); return; }
          if (now - heartbeatAt >= 12_000) {
            if (!write(': heartbeat\n\n')) return;
            heartbeatAt = now;
          }
          if (!more || step === 3) { schedule(result, more); return; }
        }
      } catch { close(); }
    };
    schedule(initial, initial.hasMore);

  });
}
