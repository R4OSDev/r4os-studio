import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import type { AttachmentListing, AttachmentReceipt, SessionAttachment } from '../../../../shared/agent-inputs.js';
import type { ProjectSessions } from '../projects/sessions.js';
import { ProjectError } from '../projects/store.js';
import { sessionStore } from './store.js';
import { attachmentStore } from './attachment-store.js';

const identity = { type: 'string', pattern: '^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$' };
const fields = { id: identity, sessionId: identity };
const params = { type: 'object', additionalProperties: false, required: ['id', 'sessionId'], properties: fields };
type Params = { id: string; sessionId: string };
const uploads = new Set<FastifyRequest>();
const previews = new Set<FastifyRequest>();
const maxFileBytes = 16 * 1024 * 1024;

export function attachmentRoutes(app: FastifyInstance, directory: string, security: ProjectSessions, ownerType: 'project' | 'skill', providers?: string) {
  const base = '/:id/sessions/:sessionId/attachments';
  const owner = (id: string) => ({ ownerType, ownerId: id });
  app.addContentTypeParser('application/octet-stream', { parseAs: 'buffer', bodyLimit: maxFileBytes }, (_request, body, done) => done(null, body));
  app.addHook('onResponse', async (request) => { uploads.delete(request); previews.delete(request); });
  app.addHook('onError', async (request) => { uploads.delete(request); previews.delete(request); });
  for (const operation of ['preview', 'download'] as const) app.get<{ Params: Params & { attachmentId: string } }>(base + '/:attachmentId/' + operation, {
    schema: { params: { ...params, required: [...params.required, 'attachmentId'], properties: { ...fields, attachmentId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    if (previews.size >= 8) throw new ProjectError('Too many image previews are open.', 429);
    previews.add(request); request.raw.once('aborted', () => previews.delete(request));
    const image = await attachmentStore<{ path: string; attachment: SessionAttachment }>(directory,
      { operation, ...owner(request.params.id), sessionId: request.params.sessionId, attachmentId: request.params.attachmentId });
    if (operation === 'preview' && (image.attachment.mode !== 'localImage' || !['image/png', 'image/jpeg', 'image/webp'].includes(image.attachment.mediaType)))
      throw new ProjectError('This attachment has no raster preview.', 415);
    const filename = encodeURIComponent(image.attachment.name).replace(/['()*]/g, value => '%' + value.charCodeAt(0).toString(16));
    return reply.header('Cache-Control', 'private, no-store').header('X-Content-Type-Options', 'nosniff')
      .header('Content-Security-Policy', "default-src 'none'; sandbox")
      .header('Content-Disposition', operation === 'preview' ? 'inline; filename="attachment-image"' : `attachment; filename="attachment"; filename*=UTF-8''${filename}`)
      .type(operation === 'preview' ? image.attachment.mediaType : 'application/octet-stream').send(createReadStream(image.path, { highWaterMark: 65536 }));
  });
  app.get<{ Params: Params }>(base, { schema: { params } }, async (request, reply) => {
    security.session(request, reply);
    return attachmentStore<AttachmentListing>(directory, { operation: 'list', ...owner(request.params.id), sessionId: request.params.sessionId });
  });
  app.get<{ Params: Params & { requestId: string } }>(base + '/uploads/:requestId', {
    schema: { params: { ...params, required: [...params.required, 'requestId'], properties: { ...fields, requestId: identity } } },
  }, async (request, reply) => {
    security.session(request, reply);
    return attachmentStore<AttachmentReceipt>(directory, { operation: 'receipt', ...owner(request.params.id), sessionId: request.params.sessionId, requestId: request.params.requestId });
  });
  app.post<{ Params: Params & { requestId: string }; Querystring: { name: string; mediaType?: string }; Body: Buffer }>(base + '/uploads/:requestId', {
    bodyLimit: maxFileBytes,
    onRequest: async (request, reply) => {
      security.mutation(request, reply);
      if (request.headers['content-type']?.split(';', 1)[0].trim() !== 'application/octet-stream' || request.headers['content-encoding'])
        throw new ProjectError('Upload raw application/octet-stream bytes without content encoding.', 415);
      if (uploads.size >= 2) throw new ProjectError('Two uploads are already in progress. Try again after one finishes.', 429);
      uploads.add(request); request.raw.once('aborted', () => uploads.delete(request));
      // Owner/session authorization precedes buffering any binary body.
      await sessionStore(directory, { operation: 'get', ...owner(request.params.id), sessionId: request.params.sessionId }, providers);
    },
    schema: { params: { ...params, required: [...params.required, 'requestId'], properties: { ...fields, requestId: identity } },
      querystring: { type: 'object', additionalProperties: false, required: ['name'], properties: {
        name: { type: 'string', minLength: 1, maxLength: 255 }, mediaType: { type: 'string', minLength: 3, maxLength: 120 },
      } } },
  }, async (request, reply) => {
    if (!Buffer.isBuffer(request.body) || !request.body.length) throw new ProjectError('Upload a nonempty binary file.', 400);
    const receipt = await attachmentStore<AttachmentReceipt>(directory, { operation: 'upload', ...owner(request.params.id), sessionId: request.params.sessionId,
      input: { requestId: request.params.requestId, name: request.query.name, mediaType: request.query.mediaType ?? 'application/octet-stream',
        size: request.body.length, sha256: createHash('sha256').update(request.body).digest('hex') } }, request.body);
    return reply.code(receipt.state === 'rejected' ? 422 : receipt.state === 'pending' || receipt.state === 'unknown' ? 202 : 200).send(receipt);
  });
  app.delete<{ Params: Params & { attachmentId: string } }>(base + '/:attachmentId', {
    schema: { params: { ...params, required: [...params.required, 'attachmentId'], properties: { ...fields, attachmentId: identity } } },
  }, async (request, reply) => {
    security.mutation(request, reply);
    return attachmentStore<{ id: string; removed: boolean }>(directory, { operation: 'remove', ...owner(request.params.id), sessionId: request.params.sessionId, attachmentId: request.params.attachmentId });
  });
}
