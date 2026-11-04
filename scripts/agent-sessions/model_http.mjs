/** One private HTTP request. No model protocol, tools, loop, retry or listener. */
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';

const MAX_REQUEST = 8 * 1024 * 1024, MAX_RESPONSE = 16 * 1024 * 1024;
const paths = { responses: '/responses', 'chat-completions': '/chat/completions', messages: '/messages' };
let request, finished = false, connected = false;
function emit(value) { return process.stdout.write(JSON.stringify(value) + '\n'); }
function fail(code = 'model_transport_error', httpStatus = null, details = null, notDispatched = false) {
  if (finished) return; finished = true;
  emit({ type: 'error', code, httpStatus, details, notDispatched }); request?.destroy();
}
process.on('SIGTERM', () => { fail('model_interrupted'); process.exitCode = 1; });
process.on('SIGINT', () => { fail('model_interrupted'); process.exitCode = 1; });

let configuration;
try {
  const chunks = []; let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > 20 * 1024 * 1024) throw Error('Bootstrap limit');
    chunks.push(chunk);
  }
  configuration = JSON.parse(Buffer.concat(chunks).toString('utf8'));
} catch { fail('model_bootstrap_invalid'); }

if (configuration && !finished) {
  try {
    const { binding, addresses, key, body, extraHeaders = {} } = configuration;
    const target = new URL(binding.baseUrl), originalHost = target.hostname.replace(/^\[|\]$/g, '');
    if (!['http:', 'https:'].includes(target.protocol) || binding.kind !== 'local' && target.protocol !== 'https:'
      || target.username || target.password || target.search || target.hash || !Object.hasOwn(paths, binding.protocol)
      || !Array.isArray(addresses) || !addresses.length || addresses.some(address => !net.isIP(address))
      || typeof body !== 'string' || Buffer.byteLength(body) > MAX_REQUEST
      || JSON.parse(body).model !== binding.model || !['none', 'bearer'].includes(binding.auth)
      || binding.auth === 'bearer' && (typeof key !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(key))) throw Error('Binding');
    if (net.isIP(originalHost) && !addresses.includes(originalHost)) throw Error('Address');
    const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream',
      'Accept-Encoding': 'identity', 'Content-Length': Buffer.byteLength(body) };
    // Only trusted connector code supplies these headers. Keep routing,
    // framing and authentication owned here, without a per-vendor registry.
    const reserved = new Set(['host', 'authorization', 'proxy-authorization', 'cookie', 'connection',
      'content-type', 'content-length', 'transfer-encoding', 'te', 'trailer', 'upgrade', 'expect', 'accept-encoding']);
    for (const [name, value] of Object.entries(extraHeaders)) {
      if (!/^[a-zA-Z0-9-]{1,80}$/.test(name) || reserved.has(name.toLowerCase())
        || typeof value !== 'string' || !/^[\x20-\x7e]{1,2048}$/.test(value)) throw Error('Header');
      headers[name] = value;
    }
    if (binding.auth === 'bearer') headers.Authorization = 'Bearer ' + key;
    const address = addresses[0], transport = target.protocol === 'https:' ? https : http;
    request = transport.request({ protocol: target.protocol, hostname: originalHost, port: target.port || undefined,
      path: target.pathname.replace(/\/$/, '') + paths[binding.protocol], method: 'POST', headers,
      agent: false, maxHeaderSize: 16384, autoSelectFamily: false, family: net.isIP(address),
      lookup: (host, options, callback) => {
        if (host !== originalHost) { callback(Error('Target changed')); return; }
        if (options.all) callback(null, [{ address, family: net.isIP(address) }]);
        else callback(null, address, net.isIP(address));
      }, rejectUnauthorized: true, servername: net.isIP(originalHost) ? undefined : originalHost,
    }, incoming => {
      const status = incoming.statusCode ?? 502;
      if (status < 200 || status >= 300) {
        const errors = []; let size = 0;
        incoming.on('data', chunk => {
          const remaining = Math.max(0, 65536 - size); size += chunk.length; errors.push(chunk.subarray(0, remaining));
          if (size > 65536) { incoming.destroy(); fail('model_http_error', status,
            { providerBodyBase64: Buffer.concat(errors).toString('base64'), bodyTruncated: true }); }
        });
        incoming.once('end', () => {
          let code = 'model_http_error';
          try {
            const payload = JSON.parse(Buffer.concat(errors).toString('utf8'));
            const value = payload.error?.code ?? payload.code;
            if (['string', 'number'].includes(typeof value) && /^[a-zA-Z0-9_.-]{1,128}$/.test(String(value))
              && (typeof key !== 'string' || !String(value).includes(key))) code = String(value);
          } catch { /* Never forward provider error text or reflected credentials. */ }
          fail(code, status, { providerBodyBase64: Buffer.concat(errors).toString('base64'),
            requestId: incoming.headers['x-request-id'] ?? incoming.headers['request-id'] ?? null,
            retryAfter: incoming.headers['retry-after'] ?? null });
        });
        incoming.once('error', () => fail('model_http_error', status));
        return;
      }
      if (!String(incoming.headers['content-type'] ?? '').startsWith('text/event-stream')
        || incoming.headers['content-encoding'] || Number(incoming.headers['content-length'] ?? 0) > MAX_RESPONSE) {
        incoming.destroy(); fail('model_stream_invalid', status); return;
      }
      let received = 0;
      incoming.on('data', chunk => {
        received += chunk.length;
        if (received > MAX_RESPONSE || finished) { incoming.destroy(); fail('model_stream_limit'); return; }
        if (!emit({ type: 'bytes', value: chunk.toString('base64') })) incoming.pause();
      });
      process.stdout.on('drain', () => incoming.resume());
      incoming.once('end', () => { if (!finished) { finished = true; emit({ type: 'end', httpStatus: status }); } });
      incoming.once('error', () => fail('model_stream_incomplete'));
      incoming.once('aborted', () => fail('model_stream_incomplete'));
    });
    request.once('error', error => {
      const unsent = !connected && ['ECONNREFUSED', 'ENETUNREACH', 'EHOSTUNREACH', 'EAI_AGAIN'].includes(error.code);
      fail('model_connection_error', null, { connectionCode: error.code }, unsent);
    });
    request.setTimeout(300000, () => fail('model_transport_timeout'));
    const connect = setTimeout(() => fail('model_transport_timeout'), 10000);
    const deadline = setTimeout(() => fail('model_transport_timeout'), 900000);
    request.on('socket', socket => socket.once(target.protocol === 'https:' ? 'secureConnect' : 'connect', () => { connected = true; clearTimeout(connect); }));
    request.once('close', () => { clearTimeout(connect); clearTimeout(deadline); });
    // Forward the exact Python-serialized body. Re-encoding parsed JavaScript
    // objects would round valid uint64 tool arguments and history values.
    request.end(body);
  } catch { fail('model_bootstrap_invalid'); }
}
