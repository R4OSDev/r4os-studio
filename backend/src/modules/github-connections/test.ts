import type { GitHubTestResult, GitHubTestStatus } from '../../../../shared/github-connections.js';

/** One bounded, read-only request. No redirect, credential import or repository access. */
export async function testToken(token: string, transport: typeof fetch = fetch, timeoutMs = 10_000): Promise<GitHubTestResult> {
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), timeoutMs);
  const result = (status: GitHubTestStatus): GitHubTestResult => ({ status, checkedAt: new Date().toISOString() });
  try {
    const response = await transport('https://api.github.com/user', { method: 'GET', redirect: 'manual',
      signal: controller.signal, credentials: 'omit', cache: 'no-store', headers: {
        Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'R4OS-Studio',
      } });
    try {
      if (response.status === 401) return result('authentication_failed');
      if (response.status === 429 || (response.status === 403 && (response.headers.get('x-ratelimit-remaining') === '0' || response.headers.has('retry-after')))) return result('rate_limited');
      if (response.status === 403) return result('forbidden');
      if (response.status >= 500) return result('server_error');
      if (response.status !== 200 || Number(response.headers.get('content-length')) > 65536 || !response.body) return result('invalid_response');
      const reader = response.body.getReader();
      const chunks: Uint8Array[] = []; let bytes = 0;
      try {
        for (;;) {
          const chunk = await reader.read();
          if (chunk.done) break;
          bytes += chunk.value.byteLength;
          if (bytes > 65536) return result('invalid_response');
          chunks.push(chunk.value);
        }
      } finally { await reader.cancel().catch(() => {}); }
      let body: { login?: unknown; id?: unknown };
      try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
      catch { return result('invalid_response'); }
      if (!body || typeof body !== 'object') return result('invalid_response');
      if (typeof body.login !== 'string' || !/^[a-z\d][a-z\d-]{0,38}(?:\[bot\])?$/i.test(body.login)
        || !Number.isSafeInteger(body.id) || (body.id as number) <= 0) return result('invalid_response');
      return { ...result('success'), login: body.login, userId: body.id as number };
    } finally { await response.body?.cancel().catch(() => {}); }
  } catch { return result(controller.signal.aborted ? 'timeout' : 'network_error'); }
  finally { controller.abort(); clearTimeout(deadline); }
}
