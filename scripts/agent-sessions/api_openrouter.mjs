/** OpenRouter's chosen plain Chat contract, explicit routing and bounded origin. */
import { ChatFault } from './api_chat.mjs';
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const bad = () => { throw new ChatFault('chat_semantics_unavailable'); };
export function routerSettings(value = {}) {
  if (!object(value) || Object.keys(value).some(k => !['order', 'only', 'allowFallbacks', 'attribution'].includes(k))) bad();
  const result = {};
  for (const field of ['order', 'only']) {
    const entries = value[field] ?? [];
    if (!Array.isArray(entries) || entries.length > 16 || new Set(entries).size !== entries.length
      || entries.some(v => typeof v !== 'string' || !/^[a-z0-9][a-z0-9_./-]{0,119}$/.test(v) || v.split('/').some(p => ['', '.', '..'].includes(p)))) bad();
    result[field] = [...entries];
  }
  if (result.only.length && result.order.some(v => !result.only.includes(v))) bad();
  result.allowFallbacks = value.allowFallbacks ?? false;
  if (typeof result.allowFallbacks !== 'boolean') bad();
  const attribution = value.attribution ?? null;
  if (attribution !== null) {
    if (!object(attribution) || Object.keys(attribution).sort().join(',') !== 'title,url'
      || typeof attribution.title !== 'string' || !/^[\x20-\x7e]{1,80}$/.test(attribution.title) || attribution.title.trim() !== attribution.title
      || typeof attribution.url !== 'string' || !/^[\x21-\x7e]{1,512}$/.test(attribution.url)) bad();
    let url; try { url = new URL(attribution.url); } catch { bad(); }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || attribution.url.includes('\\')) bad();
  }
  result.attribution = attribution; return result;
}

export function routerHeaders(settings, metadata = false) {
  const headers = metadata ? { 'X-OpenRouter-Metadata': 'enabled' } : {};
  if (settings.attribution) Object.assign(headers, { 'HTTP-Referer': settings.attribution.url, 'X-OpenRouter-Title': settings.attribution.title });
  return headers;
}

export function routerRequest(chat, settings, policy) {
  if (policy?.reasoning !== 'none') bad();
  // Native's store:false is a Responses retention directive. Chat is stateless
  // full-history input and does not document this field; never forward it as
  // an arbitrary provider parameter or pretend it controls provider logging.
  const request = { ...chat }; delete request.store;
  request.provider = { require_parameters: true, allow_fallbacks: settings.allowFallbacks,
    ...(settings.order.length ? { order: settings.order } : {}), ...(settings.only.length ? { only: settings.only } : {}) };
  return request;
}

export function routerError(code) {
  return new Map([[401, 'invalid_api_key'], [402, 'api_account_required'], [403, 'api_access_denied'],
    [429, 'rate_limit_exceeded'], [503, 'api_service_unavailable']]).get(code);
}

const bounded = (value, maximum = 256) => typeof value === 'string' && value.length > 0
  && Buffer.byteLength(value) <= maximum && !/[\p{Cc}\p{Cs}]/u.test(value) ? value : null;
export class RouterOrigin {
  constructor(requested, settings, secret) {
    this.requested = requested; this.settings = settings; this.secret = secret;
    this.model = null; this.backend = null; this.endpointModel = null; this.endpointBackend = null;
    this.strategy = null; this.attempt = null; this.reportedRequested = null;
  }
  safe(value, maximum) {
    const result = bounded(value, maximum);
    return result && (typeof this.secret !== 'string' || !result.includes(this.secret)) ? result : null;
  }
  observe(value) {
    if (value.model != null) {
      const current = this.safe(value.model); if (!current || this.model !== null && current !== this.model) throw new ChatFault('chat_protocol_error');
      this.model = current;
    }
    if (value.provider != null) {
      const current = this.safe(value.provider, 120); if (!current || this.backend !== null && current !== this.backend) throw new ChatFault('chat_protocol_error');
      this.backend = current;
    }
    const metadata = value.openrouter_metadata;
    if (metadata == null) return;
    if (!object(metadata)) throw new ChatFault('chat_protocol_error');
    if (metadata.requested != null) this.reportedRequested = this.safe(metadata.requested);
    if (metadata.strategy != null) this.strategy = this.safe(metadata.strategy, 80);
    if (metadata.attempt != null) {
      if (!Number.isSafeInteger(metadata.attempt) || metadata.attempt < 1 || metadata.attempt > 32
        || !this.settings.allowFallbacks && metadata.attempt > 1) throw new ChatFault('chat_protocol_error');
      this.attempt = metadata.attempt;
    }
    if (metadata.endpoints?.available != null) {
      const entries = metadata.endpoints.available;
      if (!Array.isArray(entries) || entries.length > 128 || entries.some(v => !object(v))) throw new ChatFault('chat_protocol_error');
      const selected = entries.filter(v => v.selected === true);
      if (selected.length > 1) throw new ChatFault('chat_protocol_error');
      if (selected.length === 1) {
        const current = selected[0];
        this.endpointModel = this.safe(current.model); this.endpointBackend = this.safe(current.provider, 120);
      }
    }
  }
  report(parser, ordinal) {
    return { event: 'origin', ordinal, requestedModel: this.requested, reportedRequested: this.reportedRequested,
      reportedModel: this.model, reportedBackend: this.backend, strategy: this.strategy, gatewayAttempt: this.attempt,
      endpointModel: this.endpointModel, endpointBackend: this.endpointBackend,
      providerResponseId: this.safe(parser.providerId), localResponseId: parser.id, finishReason: parser.finishReason,
      usage: parser.used ?? null };
  }
}
