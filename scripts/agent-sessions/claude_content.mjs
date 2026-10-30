/** Semantic input hashes exclude object order, retain block order and image bytes. */
import { createHash } from 'node:crypto';
export const INPUT_PROFILE = 'studio-claude-inputs-0.3.312-v1';
const sha = value => createHash('sha256').update(value).digest('hex');
const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

export function contentDigest(value) {
  const parts = typeof value === 'string' ? [{ type: 'text', text: value }] : value;
  if (!Array.isArray(parts) || !parts.length || parts.length > 17) throw Error('Invalid bounded native content.');
  let imageBytes = 0;
  const descriptors = parts.map(part => {
    if (part?.type === 'text' && typeof part.text === 'string' && Buffer.byteLength(part.text) <= 131072) {
      return { sha256: sha(part.text), type: 'text' };
    }
    const source = part?.source;
    if (part?.type !== 'image' || source?.type !== 'base64' || !['image/png','image/jpeg','image/webp'].includes(source.media_type)
      || typeof source.data !== 'string' || source.data.length > 5592408) throw Error('Unqualified native image content.');
    const raw = Buffer.from(source.data, 'base64');
    if (!raw.length || raw.length > 4194304 || raw.toString('base64') !== source.data) throw Error('Changed native image bytes.');
    imageBytes += raw.length;
    return { mediaType: source.media_type, sha256: sha(raw), size: raw.length, type: 'image' };
  });
  if (imageBytes > 8388608 || Buffer.byteLength(JSON.stringify(parts)) > 12582912) throw Error('Native content exceeds its bound.');
  return sha(JSON.stringify(descriptors));
}

export function preparedContent(value, requestId) {
  if (!value || Object.keys(value).sort().join(',') !== 'content,contentSha256,profileId,requestId,textSha256'
    || value.profileId !== INPUT_PROFILE || value.requestId !== requestId || !hash(value.textSha256) || !hash(value.contentSha256)
    || contentDigest(value.content) !== value.contentSha256
    || value.textSha256 !== sha('') && (value.content[0]?.type !== 'text' || sha(value.content[0].text) !== value.textSha256)) {
    throw Error('The original native content contract changed.');
  }
  return structuredClone(value);
}
