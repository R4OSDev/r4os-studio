/** One fixed metadata GET. No model request, proxy, listener or tool execution. */
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { modelCatalog } from './api_model_metadata.mjs';
import { routerSettings, routerHeaders } from './api_openrouter.mjs';
import { readFileSync } from 'node:fs';
import { ZAI_BASE } from './api_zai.mjs';

const MAX_BODY = 4 * 1024 * 1024;
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
    if (data.length > 131072) { clearTimeout(timer); process.stdin.off('data', read); reject(Error()); return; }
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
  if (binding.kind === 'zai-coding-plan' && (binding.baseUrl !== ZAI_BASE || binding.auth !== 'bearer' || binding.protocol !== 'chat-completions')) throw Error();
} catch { fail('binding'); }

const host = target.hostname.replace(/^\[|\]$/g, ''), address = addresses[0];
const headers = { Accept: 'application/json', 'Accept-Encoding': 'identity', 'User-Agent': 'R4OS-Studio-Model-Metadata', Connection: 'close' };
if (binding.auth === 'bearer') headers.Authorization = 'Bearer ' + key;
if (binding.kind === 'openrouter') Object.assign(headers, routerHeaders(routerSettings(binding.openrouter ?? {})));
if (binding.kind === 'zai-coding-plan') headers['User-Agent'] = JSON.parse(readFileSync(new URL('../../shared/zai-client.json', import.meta.url))).userAgent;
let query = '';
if (binding.kind === 'codex-subscription') {
  if (binding.baseUrl !== 'https://chatgpt.com/backend-api/codex' || binding.protocol !== 'responses' || binding.auth !== 'bearer'
    || !/^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?$/.test(input.clientVersion ?? '')
    || !input.extraHeaders || Object.keys(input.extraHeaders).sort().join() !== ['ChatGPT-Account-Id', 'User-Agent', 'originator'].sort().join()
    || Object.values(input.extraHeaders).some(value => typeof value !== 'string' || !/^[\x20-\x7e]{1,2048}$/.test(value))) fail('binding');
  Object.assign(headers, input.extraHeaders); query = '?client_version=' + encodeURIComponent(input.clientVersion);
}
request = (target.protocol === 'https:' ? https : http).request({ protocol: target.protocol, hostname: host,
  port: target.port || undefined, path: target.pathname.replace(/\/$/, '') + '/models' + query, method: 'GET', headers,
  agent: false, maxHeaderSize: 16384, autoSelectFamily: false, family: net.isIP(address),
  lookup: (hostname, options, callback) => {
    if (hostname !== host) { callback(Error()); return; }
    if (options.all) callback(null, [{ address, family: net.isIP(address) }]); else callback(null, address, net.isIP(address));
  }, rejectUnauthorized: true, servername: net.isIP(host) ? undefined : host,
}, response => {
  const status = response.statusCode ?? 502;
  if (status < 200 || status >= 300) { fail(status === 401 || status === 403 ? 'auth' : status === 402 ? 'account' : status === 429 ? 'rate_limit' : status >= 300 && status < 400 ? 'redirect' : status === 404 ? 'no_catalog' : status >= 500 ? 'unavailable' : 'http'); return; }
  if (!String(response.headers['content-type'] ?? '').startsWith('application/json') || response.headers['content-encoding']
    || Number(response.headers['content-length'] ?? 0) > MAX_BODY) { fail('format'); return; }
  const chunks = []; let count = 0;
  response.on('data', data => { count += data.length; if (count > MAX_BODY) fail('limit'); else chunks.push(data); });
  response.on('aborted', () => fail('connection')); response.on('error', () => fail('connection'));
  response.on('end', () => {
    if (finished) return;
    try {
      const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks)));
      const entries=['chatgpt-plan','codex-subscription'].includes(binding.kind)?value?.models:value?.data;
      if (!value || !Array.isArray(entries)) { fail('format'); return; }
      finish({ ok: true, ...modelCatalog(entries, binding, key, input.modelIds) });
    } catch { fail('format'); }
  });
});
request.on('error', () => fail('connection'));
request.on('socket', value => { socket = value; });
request.setTimeout(10000, () => fail('timeout'));
setTimeout(() => fail('timeout'), 15000);
request.end();
