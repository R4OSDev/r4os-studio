import { useEffect, useState } from 'react';
import type { RoadmapPage } from '../../../../shared/project-roadmaps';
import { roadmapRequest } from './api';

export function useRoadmapPage<T>(id: string, path: string, revision: number) {
  const key = `${id}:${path}:${revision}`;
  const [state, setState] = useState<{ key: string; page: RoadmapPage<T> | null; error: string }>({ key: '', page: null, error: '' });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void roadmapRequest<RoadmapPage<T>>(id, path, '', 'GET', undefined, controller.signal).then((page) => {
      if (controller.signal.aborted) return;
      setState({ key, page: page.revision === revision ? page : null,
        error: page.revision === revision ? '' : 'The roadmap changed. Refresh before continuing.' });
    }).catch((cause: Error) => { if (!controller.signal.aborted) setState({ key, page: null, error: cause.message }); });
    return () => controller.abort();
  }, [id, path, revision, key]);
  const active = state.key === key ? state : { key, page: null, error: '' };
  async function more() {
    if (busy || !active.page?.nextCursor) return;
    setBusy(true);
    try {
      const page = await roadmapRequest<RoadmapPage<T>>(id, path + '?cursor=' + encodeURIComponent(active.page.nextCursor));
      setState((old) => old.key === key && old.page ? page.revision === revision
        ? { key, page: { ...page, items: [...old.page.items, ...page.items] }, error: '' }
        : { ...old, error: 'The roadmap changed. Refresh before continuing.' } : old);
    } catch (cause) { setState((old) => old.key === key ? { ...old, error: (cause as Error).message } : old); }
    finally { setBusy(false); }
  }
  return { ...active, loading: state.key !== key, busy, more };
}
