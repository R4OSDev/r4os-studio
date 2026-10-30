import { useCallback, useEffect, useRef, useState } from 'react';
import type { AttachmentListing } from '../../../../shared/agent-inputs';
import type { useSessionApi } from './api';

/** Metadata only. Each refresh supersedes old reads, including owner/session changes. */
export function useStoredAttachments(key: string, base: string, sessionId: string, enabled: boolean,
  request: ReturnType<typeof useSessionApi>['request']) {
  const [state, setState] = useState<{ key: string; value: AttachmentListing | null; error: string }>({ key: '', value: null, error: '' });
  const timer = useRef<number | undefined>(undefined);
  const sequence = useRef({ value: 0 }), controller = useRef<AbortController | null>(null);
  const listStored = useCallback(async () => {
    window.clearTimeout(timer.current);
    const serial = ++sequence.current.value;
    controller.current?.abort(); const active = new AbortController(); controller.current = active;
    try {
      const value = await request<AttachmentListing>(base, '', 'GET', undefined, active.signal);
      if (active.signal.aborted || serial !== sequence.current.value) throw new DOMException('Upload listing superseded.', 'AbortError');
      if (!Array.isArray(value.attachments) || value.attachments.some(file => file.sessionId !== sessionId)
        || value.cleanupPending !== undefined && !Array.isArray(value.cleanupPending)) throw new Error('The stored upload listing could not be matched to this session.');
      setState({ key, value, error: '' }); return value;
    } catch (cause) {
      if (!active.signal.aborted && serial === sequence.current.value) setState(old => ({ key,
        value: old.key === key ? old.value : null, error: (cause as Error).message || 'Stored uploads could not be checked.' }));
      throw cause;
    }
  }, [key, base, sessionId, request]);
  const refreshStored = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { void listStored().catch(() => undefined); }, 50);
  }, [listStored]);
  useEffect(() => {
    const epoch = sequence.current;
    if (enabled) refreshStored();
    return () => { window.clearTimeout(timer.current); epoch.value++; controller.current?.abort(); };
  }, [enabled, refreshStored]);
  return { listStored, refreshStored, storedUploads: state.key === key ? state.value : null,
    storedError: state.key === key ? state.error : '' };
}
