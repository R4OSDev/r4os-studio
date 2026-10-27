import { useEffect, useState } from 'react';
import type { RemoteHost, RemoteHostCapabilities, RemoteHostCheck } from '../../../../shared/remote-hosts';
import type { RemoteHostsApi } from './useRemoteHosts';
import { getHost, hostCapabilities, readHostCheck, RemoteHostRequestError } from './api';
import { projectRequestId } from '../projects/api';

export function HostConnection({ host, api, changed }: { host: RemoteHost; api: RemoteHostsApi; changed: (host: RemoteHost) => void }) {
  const key = 'studio.remote.check.' + host.id;
  const accept = api.accept;
  const [capability, setCapability] = useState<RemoteHostCapabilities>();
  const [recovery] = useState(() => {
    try {
      const raw = sessionStorage.getItem(key); const value = raw ? JSON.parse(raw) as { requestId: string; revision: number } : null;
      if (value && (!/^[a-f0-9-]{36}$/.test(value.requestId) || !Number.isSafeInteger(value.revision) || value.revision < 1)) throw new Error();
      return { value, error: '' };
    } catch { return { value: null, error: 'This browser has an unrecognized connection check. Preserve its data and review before retrying.' }; }
  });
  const [pending, setPending] = useState(recovery.value), [receipt, setReceipt] = useState<RemoteHostCheck>();
  const [busy, setBusy] = useState(false), [error, setError] = useState(recovery.error), [trustRequest, setTrustRequest] = useState<{ requestId: string; revision: number } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void hostCapabilities(controller.signal).then((value) => { if (!controller.signal.aborted) setCapability(value); }).catch(() => {});
    return () => controller.abort();
  }, [host.id]);
  const requestId = pending?.requestId;
  useEffect(() => {
    if (!requestId) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined, attempts = 0;
    async function poll() {
      try {
        const value = await readHostCheck(host.id, requestId!, controller.signal);
        if (controller.signal.aborted) return;
        setReceipt(value); setError('');
        if (value.phase === 'complete' || value.phase === 'unknown') {
          const current = await getHost(host.id, controller.signal);
          if (controller.signal.aborted) return;
          changed(current); accept(current); setPending(null);
          if (value.phase === 'complete') sessionStorage.removeItem(key);
          return;
        }
      } catch (cause) { if (!controller.signal.aborted) setError((cause as Error).message); }
      if (!controller.signal.aborted && ++attempts < 30) timer = setTimeout(() => void poll(), 1000);
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [host.id, requestId, accept, changed, key]);
  async function check() {
    if (busy || !capability?.test || recovery.error) return;
    const original = pending ?? { requestId: projectRequestId(), revision: host.revision };
    try { sessionStorage.setItem(key, JSON.stringify(original)); }
    catch { setError('Enable session storage so the original connection check can be retained.'); return; }
    setPending(original); setBusy(true); setError('');
    try { setReceipt(await api.check(host, original.requestId, original.revision)); }
    catch (cause) {
      const failure = cause as RemoteHostRequestError; setError(failure.message);
      if (failure.status >= 400 && failure.status < 500) { setPending(null); sessionStorage.removeItem(key); }
    } finally { setBusy(false); }
  }
  async function reset() {
    const request = trustRequest ?? { requestId: projectRequestId(), revision: host.revision };
    if (!trustRequest && !window.confirm(`Reset trust for “${host.name}” at ${host.address}:${host.port}? Current key: ${host.hostKey.fingerprint}. The next explicit connection check will trust its first observed key.`)) return;
    setTrustRequest(request); setBusy(true); setError('');
    try { changed(await api.resetTrust(host, request.requestId, request.revision)); setTrustRequest(null); }
    catch (cause) { setError((cause as Error).message); if ((cause as RemoteHostRequestError).status < 500) setTrustRequest(null); }
    finally { setBusy(false); }
  }
  return <section aria-label="Remote connection check">
    <div className="remote-actions"><button type="button" disabled={busy || !capability?.test || !!recovery.error || !!trustRequest} onClick={() => void check()}>{busy ? trustRequest ? 'Saving trust…' : 'Checking…' : pending ? 'Retry original check' : 'Check connection'}</button>
      {host.hostKey.state === 'trusted' && <button type="button" disabled={busy || !!pending} onClick={() => void reset()}>{trustRequest ? 'Retry original trust reset' : 'Reset host trust'}</button>}</div>
    {!capability?.test && <p>{capability?.reason ?? 'Connection testing is unavailable.'}</p>}
    {host.hostKey.state === 'trusted' && <p>This key was trusted on first contact. The fingerprint is not an independent identity check.</p>}
    <p>A check runs only VER with the saved login. Past success does not guarantee that the host is available now.</p>
    {receipt && <p role="status">Check {receipt.requestId}: {receipt.phase}{receipt.invalidated ? '. Target settings changed; this result does not confirm the current host.' : ''}{receipt.message ? '. ' + receipt.message : ''}</p>}
    {error && <p role="alert" className="remote-error">{error}</p>}
  </section>;
}
