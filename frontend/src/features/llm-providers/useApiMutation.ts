import { useCallback, useRef, useState } from 'react';
import type { ApiModelMutation, ApiProviderKind, ApiProviderMutation } from '../../../../shared/api-providers';
import type { ProviderApi } from './useProviders';
import { ProviderRequestError, providerRequestId } from './api';

type Operation = 'create' | 'update' | 'disconnect' | 'delete' | 'model' | 'check';
interface Pending { requestId: string; operation: Operation; revision?: number; kind?: ApiProviderKind }
type Result = ApiModelMutation | ApiProviderMutation;
const uuid = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
function stored(key: string, models: boolean): Pending | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null') as Pending | null;
    return value && uuid.test(value.requestId) && (models ? ['model', 'check'] : ['create', 'update', 'disconnect', 'delete']).includes(value.operation)
      && Object.keys(value).every(k => ['requestId', 'operation', 'revision', 'kind'].includes(k)) ? value : null;
  } catch { return null; }
}

/** Browser storage contains original IDs only. Keys and mutation bodies stay in memory. */
export function useApiMutation(api: ProviderApi, id: string | null, models = false) {
  const request = api.request;
  const key = `studio.api.${models ? 'models' : 'provider'}.${id ?? 'new'}`;
  const [pending, setPending] = useState<Pending | null>(() => stored(key, models));
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [notFound, setNotFound] = useState(false);
  const inflight = useRef(false);
  const base = '/api-connections' + (id ? '/' + id : '');
  const accept = useCallback((result: Result) => {
    setNotFound(false);
    if (result.state === 'complete' || result.state === 'failed') { sessionStorage.removeItem(key); setPending(null); }
    if ('error' in result && result.error) setError(result.error);
    return result;
  }, [key]);
  async function send(operation: Operation, body: Record<string, unknown>, original = false): Promise<Result | undefined> {
    if (inflight.current || pending && !original || original && pending?.operation !== operation) return;
    const next = original ? pending! : { requestId: providerRequestId(), operation,
      ...(operation === 'create' ? { kind: body.kind as ApiProviderKind } : {}),
      ...(['disconnect', 'delete'].includes(operation) ? { revision: body.revision as number } : {}) };
    try { sessionStorage.setItem(key, JSON.stringify(next)); }
    catch { setError('Enable session storage to keep the original request ID before saving.'); return; }
    setPending(next); setError(''); setNotFound(false); inflight.current = true; setBusy(true);
    const suffix = operation === 'disconnect' ? '/disconnect' : operation === 'check' ? '/models/check' : operation === 'model' ? '/models' : '';
    try {
      return accept(await api.request<Result>(base + suffix, operation === 'update' ? 'PATCH' : operation === 'delete' ? 'DELETE' : 'POST', { ...body, requestId: next.requestId }));
    } catch (cause) {
      if (cause instanceof ProviderRequestError && cause.status < 500 && cause.status !== 408 && !(original && cause.status === 409)) {
        sessionStorage.removeItem(key); setPending(null);
      }
      setError(cause instanceof Error ? cause.message : 'The original request result is unavailable.');
    } finally { inflight.current = false; setBusy(false); }
  }
  const read = useCallback(async (): Promise<Result | undefined> => {
    if (!pending || inflight.current) return;
    inflight.current = true; setBusy(true); setError('');
    try {
      const path = !id ? '/api-connections/creation-requests/' + pending.requestId
        : base + (models ? '/model-requests/' : '/requests/') + pending.requestId;
      return accept(await request<Result>(path));
    } catch (cause) {
      setNotFound(cause instanceof ProviderRequestError && cause.status === 404);
      setError(cause instanceof ProviderRequestError && cause.status === 404
        ? 'The original request is not recorded yet. Read again or complete its settings and retry using the same request ID. Keys must be entered again after a reload.'
        : cause instanceof Error ? cause.message : 'The original request could not be read.');
    } finally { inflight.current = false; setBusy(false); }
  }, [pending, id, base, models, request, accept]);
  return { pending, busy, error, notFound, send, read };
}
