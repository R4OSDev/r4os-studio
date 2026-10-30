/** Private fixed-target model transport. No agent, tools, context loop or retries. */
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { timingSafeEqual } from 'node:crypto';

const MAX_REQUEST = 8 * 1024 * 1024, MAX_RESPONSE = 16 * 1024 * 1024, MAX_ERROR = 65536;
const ERROR_CODES = new Map([
  ['context_length_exceeded', 'The maximum model context length was exceeded.'],
  ['usage_limit_exceeded', 'The model usage limit was reached.'],
  ['insufficient_quota', 'The model provider quota was reached.'],
  ['rate_limit_exceeded', 'The model service is rate limited.'],
  ['invalid_api_key', 'The model provider credential was rejected.'],
  ['model_not_found', 'The configured model is unavailable.'],
]);
const sockets = new Set(), upstreams = new Set();
let server, stopped = false;
function stop() {
  if (stopped) return; stopped = true;
  for (const value of upstreams) value.destroy();
  for (const socket of sockets) socket.destroy();
  if (server) server.close(() => process.exit(0)); else process.exit(0);
}
process.on('SIGTERM', stop); process.on('SIGINT', stop);
process.stdin.on('end', stop); process.stdin.on('error', stop);

const configuration = await new Promise((resolve, reject) => {
  let raw = Buffer.alloc(0);
  const timeout = setTimeout(() => reject(Error('Bootstrap unavailable')), 5000);
  const read = chunk => {
    raw = Buffer.concat([raw, chunk]);
    if (raw.length > 65536) { clearTimeout(timeout); reject(Error('Bootstrap limit')); process.stdin.off('data', read); return; }
    const line = raw.indexOf(10); if (line < 0) return;
    clearTimeout(timeout); process.stdin.off('data', read);
    try { resolve(JSON.parse(raw.subarray(0, line).toString('utf8'))); } catch { reject(Error('Bootstrap invalid')); }
  };
  process.stdin.on('data', read);
}).catch(() => { process.stdout.write('{"error":"API transport bootstrap unavailable"}\n'); process.exit(1); });

const { binding, addresses, key, relayToken } = configuration;
let target;
try {
  target = new URL(binding.baseUrl);
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password || target.search || target.hash
    || (binding.kind !== 'local' && target.protocol !== 'https:') || binding.protocol !== 'responses'
    || !Array.isArray(addresses) || !addresses.length || addresses.length > 64 || addresses.some(value => !net.isIP(value))
    || typeof relayToken !== 'string' || !/^[a-f0-9]{64}$/.test(relayToken)
    || typeof binding.model !== 'string' || !binding.model || binding.model.length > 256
    || !['none', 'bearer'].includes(binding.auth) || (binding.auth === 'bearer' && (typeof key !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(key)))) throw Error();
  const literal = target.hostname.replace(/^\[|\]$/g, '');
  if (net.isIP(literal) && !addresses.includes(literal)) throw Error();
} catch { process.stdout.write('{"error":"API transport binding unavailable"}\n'); process.exit(1); }

function fail(response, status, code = 'provider_error') {
  if (response.destroyed) return;
  if (response.headersSent) { response.destroy(); return; }
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', Connection: 'close' });
  response.end(JSON.stringify({ error: { code, message: ERROR_CODES.get(code) ?? 'The configured model service could not complete this request.' } }));
}
function authenticated(value) {
  if (typeof value !== 'string') return false;
  const actual = Buffer.from(value), expected = Buffer.from('Bearer ' + relayToken);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

server = http.createServer({ maxHeaderSize: 16384, headersTimeout: 10000, requestTimeout: 300000 }, (request, response) => {
  if (stopped || !authenticated(request.headers.authorization)) { fail(response, 403); request.resume(); return; }
  if (request.method !== 'POST' || request.url !== '/v1/responses' || request.headers['content-encoding']
    || !String(request.headers['content-type'] ?? '').startsWith('application/json')) { fail(response, 400); request.resume(); return; }
  let size = 0; const chunks = [];
  request.on('data', chunk => {
    size += chunk.length;
    if (size > MAX_REQUEST) { fail(response, 413); request.destroy(); return; }
    chunks.push(chunk);
  });
  request.on('error', () => response.destroy());
  request.on('end', () => {
    if (response.destroyed || response.writableEnded || stopped) return;
    const body = Buffer.concat(chunks); let value;
    try {
      value = JSON.parse(body.toString('utf8'));
      if (value.model !== binding.model || value.stream !== true || value.store !== false || !Array.isArray(value.input)
        || (value.previous_response_id !== undefined && value.previous_response_id !== null && value.previous_response_id !== '')
        || value.conversation || !Array.isArray(value.tools) || value.tools.some(tool => tool.type !== 'function')) throw Error();
    } catch { fail(response, 400); return; }
    const transport = target.protocol === 'https:' ? https : http;
    const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream', 'Accept-Encoding': 'identity',
      'Content-Length': String(body.length), 'User-Agent': 'R4OS-Studio-Model-Transport', Connection: 'close' };
    if (binding.auth === 'bearer') headers.Authorization = 'Bearer ' + key;
    const originalHost = target.hostname.replace(/^\[|\]$/g, '');
    const address = addresses[0];
    // Python validates the complete DNS answer against the selected network
    // scope before bootstrap. This lookup never queries DNS again, and TLS
    // continues to verify the original hostname/SNI against the system CAs.
    const upstream = transport.request({ protocol: target.protocol, hostname: originalHost, port: target.port || undefined,
      path: target.pathname.replace(/\/$/, '') + '/responses', method: 'POST', headers, agent: false,
      maxHeaderSize: 16384, autoSelectFamily: false, family: net.isIP(address),
      lookup: (host, options, callback) => {
        if (host !== originalHost) { callback(Error('Target mismatch')); return; }
        if (options.all) callback(null, [{ address, family: net.isIP(address) }]);
        else callback(null, address, net.isIP(address));
      },
      rejectUnauthorized: true, servername: net.isIP(originalHost) ? undefined : originalHost,
    }, incoming => {
      const status = incoming.statusCode ?? 502;
      if (status < 200 || status >= 300) {
        // Redirects never trigger another request. Only allowlisted error codes
        // survive; provider text, URLs, identifiers and reflected keys do not.
        let count = 0; const errors = [];
        incoming.on('data', chunk => { count += chunk.length; if (count <= MAX_ERROR) errors.push(chunk); else incoming.destroy(); });
        const finish = () => {
          let code = 'provider_error';
          try { const name = JSON.parse(Buffer.concat(errors).toString('utf8')).error?.code; if (ERROR_CODES.has(name)) code = name; } catch { /* Safe generic failure. */ }
          fail(response, status >= 400 && status <= 599 ? status : 502, code);
        };
        incoming.once('end', finish); incoming.once('error', () => fail(response, 502)); return;
      }
      if (!String(incoming.headers['content-type'] ?? '').startsWith('text/event-stream')
        || incoming.headers['content-encoding'] || Number(incoming.headers['content-length'] ?? 0) > MAX_RESPONSE) {
        incoming.destroy(); fail(response, 502); return;
      }
      response.writeHead(status, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', Connection: 'close' });
      let received = 0;
      incoming.on('data', chunk => {
        received += chunk.length;
        if (received > MAX_RESPONSE || stopped) { incoming.destroy(); response.destroy(); return; }
        if (!response.write(chunk)) incoming.pause();
      });
      response.on('drain', () => incoming.resume());
      incoming.on('end', () => response.end());
      incoming.on('error', () => response.destroy());
      incoming.on('aborted', () => response.destroy());
    });
    upstreams.add(upstream); upstream.on('close', () => upstreams.delete(upstream));
    upstream.on('error', () => fail(response, 502));
    const connectTimer = setTimeout(() => { upstream.destroy(); fail(response, 504); }, 10000);
    upstream.on('socket', socket => {
      const event = target.protocol === 'https:' ? 'secureConnect' : 'connect';
      socket.once(event, () => clearTimeout(connectTimer));
    });
    upstream.on('close', () => clearTimeout(connectTimer));
    upstream.setTimeout(300000, () => { upstream.destroy(); fail(response, 504); });
    response.on('close', () => { if (!response.writableEnded) upstream.destroy(); });
    // Exactly one HTTP request. No redirect, auth, transport or status retry.
    upstream.end(body);
  });
});
server.on('connection', socket => { sockets.add(socket); socket.once('close', () => sockets.delete(socket)); });
server.on('clientError', (_error, socket) => socket.destroy());
server.on('error', stop);
server.listen(0, '127.0.0.1', () => {
  process.stdout.write(JSON.stringify({ port: server.address().port }) + '\n');
});
