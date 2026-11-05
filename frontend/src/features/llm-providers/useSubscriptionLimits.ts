import { useCallback, useEffect, useRef, useState } from 'react';
import type { ZaiQuotaMutation, ZaiSubscriptionLimits } from '../../../../shared/zai-subscription';
import { providerRequestId } from './api';

export type SubscriptionRequest = <T>(suffix: string, method?: string, body?: unknown) => Promise<T>;
interface Original { requestId: string; providerRevision: number }
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function original(key: string): Original | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null') as Original | null;
    return value && uuid.test(value.requestId) && Number.isSafeInteger(value.providerRevision) && value.providerRevision > 0
      && Object.keys(value).length === 2 ? value : null;
  } catch { return null; }
}

/** Only original request IDs/revisions are persisted. Refresh never starts inference. */
export function useSubscriptionLimits<T extends { configRevision: number; state: 'current' | 'stale' | 'unknown' } = ZaiSubscriptionLimits>(providerId: string, request: SubscriptionRequest, sharedSample?: T | null, revision?: number) {
  const key = 'studio.subscription.quota.' + providerId, legacyKey = 'studio.zai.quota.' + providerId;
  const [localSample, setSample] = useState<T | null>(null);
  const managed = sharedSample !== undefined, sample = managed ? sharedSample : localSample;
  const [pending, setPending] = useState<Original | null>(() => original(key) ?? original(legacyKey));
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [notFound, setNotFound] = useState(false);
  const inflight = useRef(false), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const read = useCallback(async () => {
    const next = await request<T | null>('/limits');
    if (mounted.current) { setSample(next); setLoading(false); setError(''); }
    return next;
  }, [request]);
  useEffect(() => {
    if (managed) return;
    let active = true;
    const reload = () => {
      if (document.hidden) return;
      void read().catch(cause => {
        if (!active) return;
        const message = cause instanceof Error ? cause.message : 'Subscription limits are unavailable.';
        setSample(previous => (cause as { status?: number }).status === 409 ? null : previous ? { ...previous, state: 'stale' } : null);
        setError(message); setLoading(false);
      });
    };
    reload(); const timer = setInterval(reload, 15000);
    return () => { active = false; clearInterval(timer); };
  }, [read, managed]);
  const accept = useCallback(async (result: ZaiQuotaMutation) => {
    if (!mounted.current) return;
    setNotFound(false);
    if (result.state === 'complete' || result.state === 'failed') {
      sessionStorage.removeItem(key); sessionStorage.removeItem(legacyKey); setPending(null);
      setError(result.error ?? '');
      await read();
    }
  }, [key, legacyKey, read]);
  const recover = useCallback(async () => {
    if (!pending || inflight.current) return;
    inflight.current = true; setBusy(true);
    try { await accept(await request<ZaiQuotaMutation>('/requests/' + pending.requestId)); }
    catch (cause) {
      if (mounted.current) {
        setNotFound((cause as { status?: number }).status === 404);
        setError(cause instanceof Error ? cause.message : 'The original limit check could not be read.');
      }
    } finally { inflight.current = false; if (mounted.current) setBusy(false); }
  }, [pending, request, accept]);
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => { if (!document.hidden) void recover(); }, 2000);
    return () => clearInterval(timer);
  }, [pending, recover]);
  async function refresh() {
    if (inflight.current || !sample && revision === undefined) return;
    if (pending && !notFound) { await recover(); return; }
    const next = pending ?? { requestId: providerRequestId(), providerRevision: sample?.configRevision ?? revision! };
    try { sessionStorage.setItem(key, JSON.stringify(next)); }
    catch { setError('Enable session storage to preserve the original limit check.'); return; }
    setPending(next); setBusy(true); setError(''); inflight.current = true;
    try { await accept(await request<ZaiQuotaMutation>('/check', 'POST', next)); }
    catch (cause) {
      const status = (cause as { status?: number }).status;
      if (status && status >= 400 && status < 500 && status !== 408) { sessionStorage.removeItem(key); sessionStorage.removeItem(legacyKey); setPending(null); }
      setError(cause instanceof Error ? cause.message : 'The original limit check is unconfirmed. Read it before another check.');
    } finally { inflight.current = false; if (mounted.current) setBusy(false); }
  }
  return { sample, loading: managed ? false : loading, busy, error, pending: !!pending, notFound, refresh, recover };
}
