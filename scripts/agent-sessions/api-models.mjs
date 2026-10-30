/** One fixed metadata GET. No model request, proxy, listener or tool execution. */
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';

const MAX_BODY = 4 * 1024 * 1024, MAX_MODELS = 256;
let request, socket, finished = false;
function finish(value) {
  if (finished) return; finished = true;
  if (request) request.destroy(); if (socket) socket.destroy();
  process.stdout.write(JSON.stringify(value) + '\n', () => process.exit(0));
}
const fail = code => finish({ ok: false, code });
process.on('SIGTERM', () => fail('cancelled')); process.on('SIGINT', () => fail('cancelled'));
process.stdin.on('end', () => fail('cancelled')); process.stdin.on('error', () => fail('cancelled'));
const input = await new Promise((resolve, reject) => {
  let data = Buffer.alloc(0); const timer = setTimeout(() => reject(Error()), 5000);
  const read = chunk => {
    data = Buffer.concat([data, chunk]);
    if (data.length > 65536) { clearTimeout(timer); process.stdin.off('data', read); reject(Error()); return; }
    const line = data.indexOf(10); if (line < 0) return;
    clearTimeout(timer); process.stdin.off('data', read);
    try { resolve(JSON.parse(data.subarray(0, line).toString('utf8'))); } catch { reject(Error()); }
  };
  process.stdin.on('data', read);
}).catch(() => { fail('binding'); });
if (!input) process.exit(1);
const { binding, addresses, key } = input;
let target;
try {
  target = new URL(binding.baseUrl);
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password || target.search || target.hash
    || binding.kind !== 'local' && target.protocol !== 'https:' || !['none', 'bearer'].includes(binding.auth)
    || binding.auth === 'bearer' && (typeof key !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(key))
    || !Array.isArray(addresses) || !addresses.length || addresses.length > 64 || addresses.some(value => !net.isIP(value))) throw Error();
  const literal = target.hostname.replace(/^\[|\]$/g, '');
  if (net.isIP(literal) && !addresses.includes(literal)) throw Error();
} catch { fail('binding'); }

function safeString(value, maximum) {
  if (typeof value !== 'string' || !value.length || value.length > maximum || /[\ud800-\udfff]/u.test(value)) return null;
  for (const char of value) if (char.codePointAt(0) < 32 || char.codePointAt(0) === 127) return null;
  if (typeof key === 'string' && value.includes(key)) return null;
  return value;
}
const tokens = value => Number.isSafeInteger(value) && value > 0 && value <= 2147483647 ? value : null;
function model(entry) {
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
  const id = safeString(entry.id, 200); if (!id || [...id].some(char => /\s/u.test(char))) return null;
  const capabilities = Object.fromEntries(['text', 'functionTools', 'streaming', 'imageInput', 'reasoning', 'webSearch', 'imageGeneration', 'goals'].map(field => [field, 'unknown']));
  let contextWindow = null, maxOutputTokens = null, name = id;
  // OpenRouter's published model schema supplies these facts. Generic Models
  // IDs alone establish no context/tool/reasoning or modality capabilities.
  if (binding.kind === 'openrouter') {
    name = safeString(entry.name, 200) ?? id;
    contextWindow = tokens(entry.context_length); maxOutputTokens = tokens(entry.top_provider?.max_completion_tokens);
    const modalities = entry.architecture?.input_modalities, outputs = entry.architecture?.output_modalities;
    if (Array.isArray(modalities) && modalities.every(value => typeof value === 'string')) {
      if (Array.isArray(outputs) && outputs.every(value => typeof value === 'string')) capabilities.text = modalities.includes('text') && outputs.includes('text') ? 'supported' : 'unsupported';
      capabilities.imageInput = modalities.includes('image') ? 'supported' : 'unsupported';
    }
    const parameters = entry.supported_parameters;
    if (Array.isArray(parameters) && parameters.length <= 128 && parameters.every(value => typeof value === 'string')) {
      capabilities.functionTools = parameters.includes('tools') && parameters.includes('tool_choice') ? 'supported' : 'unsupported';
      capabilities.reasoning = parameters.some(value => ['reasoning', 'reasoning_effort', 'include_reasoning'].includes(value)) ? 'supported' : 'unsupported';
    }
    capabilities.streaming = 'supported'; // Published endpoint-level streaming contract.
  }
  return { id, name, contextWindow, maxOutputTokens, capabilities, efforts: [], defaultEffort: null };
}
const host = target.hostname.replace(/^\[|\]$/g, ''), address = addresses[0];
const headers = { Accept: 'application/json', 'Accept-Encoding': 'identity', 'User-Agent': 'R4OS-Studio-Model-Metadata', Connection: 'close' };
if (binding.auth === 'bearer') headers.Authorization = 'Bearer ' + key;
request = (target.protocol === 'https:' ? https : http).request({ protocol: target.protocol, hostname: host,
  port: target.port || undefined, path: target.pathname.replace(/\/$/, '') + '/models', method: 'GET', headers,
  agent: false, maxHeaderSize: 16384, autoSelectFamily: false, family: net.isIP(address),
  lookup: (hostname, options, callback) => {
    if (hostname !== host) { callback(Error()); return; }
    if (options.all) callback(null, [{ address, family: net.isIP(address) }]); else callback(null, address, net.isIP(address));
  }, rejectUnauthorized: true, servername: net.isIP(host) ? undefined : host,
}, response => {
  const status = response.statusCode ?? 502;
  if (status < 200 || status >= 300) { fail(status === 401 || status === 403 ? 'auth' : status === 402 ? 'account' : status === 429 ? 'rate_limit' : status >= 300 && status < 400 ? 'redirect' : status === 404 ? 'no_catalog' : 'http'); return; }
  if (!String(response.headers['content-type'] ?? '').startsWith('application/json') || response.headers['content-encoding']
    || Number(response.headers['content-length'] ?? 0) > MAX_BODY) { fail('format'); return; }
  const chunks = []; let count = 0;
  response.on('data', data => { count += data.length; if (count > MAX_BODY) fail('limit'); else chunks.push(data); });
  response.on('aborted', () => fail('connection')); response.on('error', () => fail('connection'));
  response.on('end', () => {
    if (finished) return;
    try {
      const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks)));
      if (!value || !Array.isArray(value.data)) { fail('format'); return; }
      const seen = new Set(), values = [];
      for (const entry of value.data.slice(0, MAX_MODELS)) {
        const current = model(entry); if (!current) continue;
        if (seen.has(current.id)) { fail('duplicate'); return; } seen.add(current.id); values.push(current);
      }
      finish({ ok: true, models: values, truncated: value.data.length > MAX_MODELS });
    } catch { fail('format'); }
  });
});
request.on('error', () => fail('connection'));
request.on('socket', value => { socket = value; });
request.setTimeout(10000, () => fail('timeout'));
setTimeout(() => fail('timeout'), 15000);
request.end();
