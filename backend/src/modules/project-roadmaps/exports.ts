import { spawn } from 'node:child_process';
import { PassThrough } from 'node:stream';
import { fileURLToPath } from 'node:url';
import type { FastifyInstance, FastifyReply } from 'fastify';
import type { RoadmapExport, RoadmapExportInput } from '../../../../shared/project-roadmaps.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { roadmapStore } from './store.js';

const uuid = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const params = { type: 'object', required: ['id', 'exportId'], properties: { id: uuid, exportId: uuid } };

export function roadmapExportRoutes(app: FastifyInstance, directory: string, sessions: ProjectSessions) {
  const active = new Set<ReturnType<typeof spawn>>();
  app.addHook('onClose', async () => { for (const child of active) child.kill('SIGTERM'); });
  app.post<{ Params: { id: string }; Body: RoadmapExportInput }>('/:id/roadmap/exports', {
    bodyLimit: 8192,
    preValidation: async (request) => {
      const body = request.body;
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).length !== 4
        || Object.keys(body).some((key) => !['requestId', 'versionId', 'expectedRevision', 'currentVersionId'].includes(key))
        || !Number.isSafeInteger(body.expectedRevision)
        || ['requestId', 'versionId', 'currentVersionId'].some((key) => typeof body[key as keyof RoadmapExportInput] !== 'string')) {
        throw new ProjectError('Use the selected version, current binding, revision and request ID to export.', 400);
      }
    },
    schema: { params: { type: 'object', required: ['id'], properties: { id: uuid } }, body: {
      type: 'object', additionalProperties: false, required: ['requestId', 'versionId', 'expectedRevision', 'currentVersionId'],
      properties: { requestId: uuid, versionId: uuid, expectedRevision: { type: 'integer', minimum: 1, maximum: Number.MAX_SAFE_INTEGER }, currentVersionId: uuid },
    } },
  }, async (request, reply) => {
    sessions.mutation(request, reply);
    return roadmapStore<RoadmapExport>(directory, { operation: 'export', projectId: request.params.id, input: request.body });
  });
  app.get<{ Params: { id: string; exportId: string } }>('/:id/roadmap/exports/:exportId', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    return roadmapStore<RoadmapExport>(directory, { operation: 'export_info', projectId: request.params.id, exportId: request.params.exportId });
  });
  app.get<{ Params: { id: string; exportId: string } }>('/:id/roadmap/exports/:exportId/content', { schema: { params } }, async (request, reply) => {
    sessions.session(request, reply);
    if (active.size >= 2) throw new ProjectError('Two roadmap downloads are already active. Retry shortly.', 429);
    const info = await roadmapStore<RoadmapExport>(directory, { operation: 'export_info', projectId: request.params.id, exportId: request.params.exportId });
    return download(request.params.id, info, reply);
  });

  async function download(projectId: string, info: RoadmapExport, reply: FastifyReply) {
    if (active.size >= 2) throw new ProjectError('Two roadmap downloads are already active. Retry shortly.', 429);
    const child = spawn('/usr/bin/python3', ['-B', fileURLToPath(new URL('../../../../scripts/project-roadmaps/stream_export.py', import.meta.url)), directory, projectId, info.id],
      { stdio: ['ignore', 'pipe', 'ignore'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' } });
    active.add(child);
    const output = new PassThrough({ highWaterMark: 65536 });
    let header = Buffer.alloc(0), remainder = Buffer.alloc(0), started = false;
    const stop = () => { if (child.exitCode === null) child.kill('SIGTERM'); };
    output.on('error', stop);
    const totalTimer = setTimeout(stop, 300_000);
    child.on('close', (code) => {
      active.delete(child); clearTimeout(totalTimer);
      if (started && code !== 0) output.destroy(new Error('The archive download was interrupted.'));
    });
    reply.raw.once('close', stop);
    try {
      const ready = await new Promise<RoadmapExport>((resolve, reject) => {
        const timer = setTimeout(() => { stop(); reject(new ProjectError('The archive could not be verified in time.')); }, 10_000);
        const fail = () => { clearTimeout(timer); reject(new ProjectError('The archive download is unavailable.')); };
        child.once('error', fail);
        child.once('close', () => { if (!started) fail(); });
        const parse = (chunk: Buffer) => {
          header = Buffer.concat([header, chunk]);
          const newline = header.indexOf(10);
          if (newline < 0) {
            if (header.length > 16384) { stop(); fail(); }
            return;
          }
          child.stdout.pause(); child.stdout.removeListener('data', parse); clearTimeout(timer);
          if (newline > 16384) { stop(); fail(); return; }
          try {
            const value = JSON.parse(header.subarray(0, newline).toString('utf8'));
            if (value.error) { reject(new ProjectError(value.error, value.code)); return; }
            remainder = header.subarray(newline + 1); header = Buffer.alloc(0); started = true;
            resolve(value.result);
          } catch { stop(); fail(); }
        };
        child.stdout.on('data', parse);
      });
      if (ready.sha256 !== info.sha256 || ready.byteLength !== info.byteLength || ready.id !== info.id || ready.filename !== info.filename) {
        throw new ProjectError('The archive changed before download. Existing data was preserved.');
      }
      reply.header('Content-Type', 'text/plain; charset=utf-8').header('Content-Disposition', `attachment; filename="${info.filename}"`)
        .header('Content-Length', info.byteLength).header('X-Content-SHA256', info.sha256);
      if (remainder.length) output.write(remainder);
      child.stdout.pipe(output);
      return reply.send(output);
    } catch (error) { stop(); throw error; }
  }
}
