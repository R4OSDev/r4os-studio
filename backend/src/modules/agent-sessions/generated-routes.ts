import { createReadStream } from 'node:fs';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import type { GeneratedImage } from '../../../../shared/generated-images.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { attachmentStore } from './attachment-store.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const fields = { id: identity, sessionId: identity };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: fields };
type Params = { id: string; sessionId: string };
const streams = new Set<FastifyRequest>();

export function generatedRoutes(app: FastifyInstance, directory: string, security: ProjectSessions, ownerType: 'project' | 'skill') {
  const base = '/:id/sessions/:sessionId/generated-images';
  const owner = (id: string) => ({ ownerType, ownerId: id });
  app.addHook('onResponse', async request => { streams.delete(request); });
  app.addHook('onError', async request => { streams.delete(request); });
  app.get<{ Params: Params }>(base, { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return attachmentStore<{ images: GeneratedImage[] }>(directory, { operation: 'generated_list', ...owner(request.params.id), sessionId: request.params.sessionId });
  });
  for (const mode of ['preview', 'download'] as const) app.get<{ Params: Params & { imageId: string } }>(base + '/:imageId/' + mode, {
    schema: { params: { ...params, required: [...params.required, 'imageId'], properties: { ...fields, imageId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    if (streams.size >= 8) throw new ProjectError('Too many generated image reads are open.', 429);
    streams.add(request); request.raw.once('aborted', () => streams.delete(request));
    const result = await attachmentStore<{ path: string; image: GeneratedImage }>(directory, { operation: 'generated_access', ...owner(request.params.id), sessionId: request.params.sessionId, imageId: request.params.imageId });
    if (result.image.sessionId !== request.params.sessionId || result.image.id !== request.params.imageId || result.image.mediaType !== 'image/png'
      || !Number.isSafeInteger(result.image.size) || result.image.size < 1 || result.image.size > 16 * 1024 * 1024)
      throw new ProjectError('This reference is not a confirmed generated image in this session.', 403);
    return reply.header('Cache-Control', 'private, no-store').header('X-Content-Type-Options', 'nosniff')
      .header('Content-Security-Policy', "default-src 'none'; sandbox")
      .header('Content-Disposition', `${mode === 'preview' ? 'inline' : 'attachment'}; filename="generated-image-${result.image.id}.png"`)
      .type('image/png').send(createReadStream(result.path, { highWaterMark: 65536 }));
  });
}
