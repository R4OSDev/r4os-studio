import { request } from 'node:http';
import { createHash, timingSafeEqual } from 'node:crypto';

export interface BrowserLogin { authorizationUrl: string; callback: string; state: string; submission?: string }

export function browserLogin(value: unknown): BrowserLogin {
  if (typeof value !== 'string' || value.length > 16384) throw new Error('Invalid authorization URL.');
  const auth = new URL(value);
  if (auth.protocol !== 'https:' || auth.hostname !== 'auth.openai.com' || auth.username || auth.password || auth.hash) throw new Error('Invalid authorization URL.');
  const callback = new URL(auth.searchParams.get('redirect_uri') ?? '');
  const state = auth.searchParams.get('state');
  if (callback.protocol !== 'http:' || !['localhost', '127.0.0.1'].includes(callback.hostname)
    || !callback.port || callback.pathname !== '/auth/callback' || callback.search || callback.hash
    || callback.username || callback.password || !state || state.length > 2048
    || auth.searchParams.getAll('state').length !== 1 || auth.searchParams.getAll('redirect_uri').length !== 1) throw new Error('Invalid callback binding.');
  return { authorizationUrl: auth.toString(), callback: callback.toString(), state };
}

export function redirectSubmission(login: BrowserLogin, value: string) {
  if (value.length > 16384) throw new Error('Invalid redirect address.');
  const callback = new URL(login.callback), supplied = new URL(value);
  const state = supplied.searchParams.get('state');
  if (supplied.origin !== callback.origin || supplied.pathname !== callback.pathname
    || supplied.username || supplied.password || supplied.hash || !state
    || supplied.searchParams.getAll('state').length !== 1
    || supplied.searchParams.getAll('code').length !== 1 || !supplied.searchParams.get('code')) throw new Error('This address does not belong to the original sign-in.');
  const left = Buffer.from(state), right = Buffer.from(login.state);
  if (left.length !== right.length || !timingSafeEqual(left, right)) throw new Error('This address does not belong to the original sign-in.');
  const fingerprint = createHash('sha256').update(supplied.search).digest('hex');
  if (login.submission && login.submission !== fingerprint) throw new Error('A different redirect was already submitted. Read the original sign-in status.');
  return { fingerprint, port: Number(callback.port), path: callback.pathname + supplied.search };
}

/** Original callback, then at most its own local success page; no code replay. */
export function relayRedirect(port: number, path: string): Promise<void> {
  return localPage(port, path, true);
}

function localPage(port: number, path: string, callback: boolean): Promise<void> {
  return new Promise((resolve, reject) => {
    const current = request({ hostname: '127.0.0.1', port, path, method: 'GET', agent: false,
      headers: { Host: `127.0.0.1:${port}` }, maxHeaderSize: 16384 }, response => {
      let size = 0;
      response.on('data', (chunk: Buffer) => { size += chunk.length; if (size > 65536) response.destroy(); });
      response.on('end', () => {
        if (!response.statusCode || response.statusCode >= 400) { reject(new Error('Original callback did not confirm completion.')); return; }
        if (callback && response.statusCode === 302 && response.headers.location) {
          try {
            const next = new URL(response.headers.location);
            if (next.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(next.hostname)
              && Number(next.port) === port && next.pathname === '/success' && !next.username && !next.password && !next.hash) {
              void localPage(port, next.pathname + next.search, false).then(resolve, reject); return;
            }
          } catch { /* Never forward an invalid or external redirect. */ }
        }
        resolve(); // The native completion notification remains authoritative.
      });
      response.on('error', () => reject(new Error('Original callback completion is unconfirmed.')));
    });
    current.setTimeout(15000, () => current.destroy(new Error('Original callback timed out.')));
    current.on('error', () => reject(new Error('Original callback completion is unconfirmed.')));
    current.end();
  });
}
