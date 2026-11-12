import { createHash } from 'node:crypto';
import { constants, readFileSync } from 'node:fs';
import { open } from 'node:fs/promises';
import type { DevelopmentEvidence } from '../../../../shared/project-development.js';
import { ProjectError } from '../projects/store.js';
import { developmentHost } from './host.js';

const limits = JSON.parse(readFileSync(new URL('../../../../shared/development-host.json', import.meta.url), 'utf8')).limits;

export interface EvidenceMedia {
  metadata: DevelopmentEvidence & { jobId: string; projectId: string; source?: string; scope?: string;
    observer?: { sessionId: string; agentRunId: string }; captureOrigin?: { requestId: string; operation: string } };
  base64?: string;
  mediaType?: 'image/webp';
  previewError?: string;
  path?: string;
}

export async function readEvidence(request: Record<string, unknown>, original = false) {
  try {
    return await developmentHost<EvidenceMedia>({ ...request, [original ? 'screenshotOriginal' : 'screenshotPreview']: true });
  } catch (error) {
    if (!(error instanceof ProjectError) || error.statusCode !== 400
        || error.message !== 'Unsupported development coordinator operation.') throw error;
    return developmentHost<EvidenceMedia>(request);
  }
}

async function originalBytes(path: string, size: number) {
  const file = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const info = await file.stat();
    if (!info.isFile() || info.nlink !== 1 || info.size !== size) throw new Error('Original size changed.');
    const buffer = Buffer.alloc(size + 1);
    let offset = 0;
    while (offset < buffer.length) {
      const { bytesRead } = await file.read(buffer, offset, buffer.length - offset, offset);
      if (!bytesRead) break;
      offset += bytesRead;
    }
    return buffer.subarray(0, offset);
  } finally { await file.close(); }
}

export async function screenshotPayload(image: EvidenceMedia, original = false) {
  const { metadata } = image;
  if (image.previewError && !original) throw new ProjectError(image.previewError, 413);
  const webp = !original && image.mediaType === 'image/webp';
  const media = webp ? metadata.preview : metadata;
  const limit = original ? limits.screenshotOriginalBytes : limits.screenshotBytes;
  const invalid = () => new ProjectError('The saved screenshot bytes could not be confirmed.', 409);
  if (metadata.kind !== 'screenshot' || !media || !Number.isSafeInteger(media.bytes) || media.bytes < 1 || media.bytes > limit)
    throw invalid();
  let data: Buffer;
  try { data = original && image.path ? await originalBytes(image.path, media.bytes) : Buffer.from(image.base64 ?? '', 'base64'); }
  catch { throw invalid(); }
  if (data.length !== media.bytes || createHash('sha256').update(data).digest('hex') !== media.sha256) throw invalid();
  if (webp) {
    if (metadata.preview?.error || data.length < 20 || data.toString('ascii', 0, 4) !== 'RIFF'
        || data.toString('ascii', 8, 12) !== 'WEBP' || data.readUInt32LE(4) + 8 !== data.length) throw invalid();
  } else if (data.length < 33 || data.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a' || data.toString('ascii', 12, 16) !== 'IHDR'
      || data.readUInt32BE(16) !== metadata.width || data.readUInt32BE(20) !== metadata.height) throw invalid();
  return { data, mediaType: webp ? 'image/webp' : 'image/png', filename: webp ? 'screenshot.webp' : 'screenshot.png' };
}
