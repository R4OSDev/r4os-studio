/** Fixed subscription-monitor GET. Native auth differs from model Bearer auth.
 * Endpoint/auth contract: zai-org/zai-coding-plugins, Apache-2.0,
 * 0446d0bb0bc537d97d3ab3664c4b8b9c4a0e1254. See THIRD-PARTY-ZAI.md.
 */
import https from 'node:https';
import net from 'node:net';
import { ZAI_BASE } from './api_zai.mjs';
let request, finished = false;
const finish = value => {
  if (finished) return; finished = true; request?.destroy();
  process.stdout.write(JSON.stringify(value) + '\n', () => process.exit(0));
};
const fail = code => finish({ ok: false, code });
process.on('SIGTERM', () => fail('cancelled')); process.on('SIGINT', () => fail('cancelled'));
process.stdin.on('end', () => fail('cancelled'));
const input = await new Promise(resolve => {
  let raw = ''; const timer = setTimeout(() => resolve(null), 5000);
  const read = chunk => {
    raw += chunk;
    if (Buffer.byteLength(raw) > 65536) { clearTimeout(timer); process.stdin.off('data', read); resolve(null); return; }
    if (!raw.includes('\n')) return;
    clearTimeout(timer); process.stdin.off('data', read);
    try { resolve(JSON.parse(raw.slice(0, raw.indexOf('\n')))); } catch { resolve(null); }
  };
  process.stdin.on('data', read);
});
if (!input || input.binding?.kind !== 'zai-coding-plan' || input.binding.baseUrl !== ZAI_BASE
  || input.binding.auth !== 'bearer' || input.binding.protocol !== 'chat-completions'
  || typeof input.key !== 'string' || !/^[\x21-\x7e]{1,8192}$/.test(input.key)
  || !Array.isArray(input.addresses) || !input.addresses.length || input.addresses.length > 64 || input.addresses.some(value => !net.isIP(value))) fail('format');
if (finished) process.exit(0);
const address = input.addresses[0], host = 'api.z.ai';
request = https.request({ hostname: host, port: 443, path: '/api/monitor/usage/quota/limit', method: 'GET',
  headers: { Authorization: input.key, 'Accept-Language': 'en-US,en', 'Content-Type': 'application/json', Accept: 'application/json', 'Accept-Encoding': 'identity', Connection: 'close' },
  agent: false, maxHeaderSize: 16384, autoSelectFamily: false, family: net.isIP(address),
  lookup: (hostname, options, callback) => {
    if (hostname !== host) { callback(Error()); return; }
    if (options.all) callback(null, [{ address, family: net.isIP(address) }]); else callback(null, address, net.isIP(address));
  }, servername: host, rejectUnauthorized: true,
}, response => {
  if (response.statusCode !== 200) { fail([401,403].includes(response.statusCode) ? 'auth' : 'service'); return; }
  if (!String(response.headers['content-type'] ?? '').startsWith('application/json') || response.headers['content-encoding']) { fail('format'); return; }
  const chunks = []; let bytes = 0;
  response.on('data', chunk => { bytes += chunk.length; if (bytes > 262144) fail('format'); else chunks.push(chunk); });
  response.on('error', () => fail('service')); response.on('aborted', () => fail('service'));
  response.on('end', () => {
    try {
      const raw = new TextDecoder('utf8', { fatal: true }).decode(Buffer.concat(chunks));
      if (raw.includes(input.key)) { fail('format'); return; }
      finish({ ok: true, body: JSON.parse(raw) });
    } catch { fail('format'); }
  });
});
request.on('error', () => fail('service')); request.setTimeout(10000, () => fail('timeout'));
setTimeout(() => fail('timeout'), 15000); request.end();
