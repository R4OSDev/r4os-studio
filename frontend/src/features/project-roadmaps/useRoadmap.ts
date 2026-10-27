import { useCallback, useEffect, useState } from 'react';
import type { RoadmapBinding, RoadmapOverview, RoadmapVersionHeader } from '../../../../shared/project-roadmaps';
import * as api from './api';

interface State { key: string; overview: RoadmapOverview | null; version: RoadmapVersionHeader | null; error: string }
export function useRoadmap(id: string | null, versionId?: string) {
  const [epoch, setEpoch] = useState(0);
  const key = `${id}:${versionId ?? ''}:${epoch}`;
  const [state, setState] = useState<State>({ key: '', overview: null, version: null, error: '' });
  const [paging, setPaging] = useState(false);
  const [changedKey, setChangedKey] = useState('');
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    void api.overview(id, controller.signal).then(async (overview) => {
      let version: RoadmapVersionHeader | null = null, error = '';
      if (overview.exists && versionId) {
        try {
          const detail = await api.version(id, versionId, controller.signal);
          if (detail.revision !== overview.roadmap.revision || detail.currentVersionId !== overview.roadmap.currentVersionId) {
            throw new Error('The roadmap changed while loading. Refresh before continuing.');
          }
          version = detail.entity;
        }
        catch (cause) { error = (cause as Error).message; }
      }
      if (!controller.signal.aborted) setState({ key, overview, version, error });
    }).catch((cause: Error) => { if (!controller.signal.aborted) setState({ key, overview: null, version: null, error: cause.message }); });
    return () => controller.abort();
  }, [id, versionId, epoch, key]);
  const reload = useCallback(() => setEpoch((value) => value + 1), []);
  const active = state.key === key ? state : { key, overview: null, version: null, error: '' };
  const revision = active.overview?.exists ? active.overview.roadmap.revision : null;
  const currentVersionId = active.overview?.exists ? active.overview.roadmap.currentVersionId : null;
  useEffect(() => {
    if (!id || state.key !== key) return;
    const controller = new AbortController(); let pending = false;
    const timer = window.setInterval(() => {
      if (document.hidden || pending) return;
      pending = true;
      void api.roadmapRequest<RoadmapBinding>(id, '/revision', '', 'GET', undefined, controller.signal).then((value) => {
        if (!controller.signal.aborted && (value.revision !== revision || value.currentVersionId !== currentVersionId)) setChangedKey(`${key}:${revision}:${currentVersionId}`);
      }).catch(() => { /* A failed check never overwrites an open draft. */ }).finally(() => { pending = false; });
    }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [id, key, state.key, revision, currentVersionId]);
  async function more() {
    if (!id || paging || !active.overview?.exists || !active.overview.versions.nextCursor) return;
    const cursor = active.overview.versions.nextCursor;
    setPaging(true);
    try {
      const page = await api.versionPage(id, cursor);
      setState((previous) => {
        if (previous.key !== key || !previous.overview?.exists) return previous;
        if (page.revision !== previous.overview.roadmap.revision) return { ...previous, error: 'The roadmap changed. Refresh before continuing.' };
        return { ...previous, overview: { ...previous.overview, versions: { ...page, items: [...previous.overview.versions.items, ...page.items] } } };
      });
    } catch (cause) {
      setState((previous) => previous.key === key ? { ...previous, error: (cause as Error).message } : previous);
    } finally { setPaging(false); }
  }
  return { ...active, loading: !!id && state.key !== key, paging, more, reload, epoch, remoteChanged: changedKey === `${key}:${revision}:${currentVersionId}` };
}
export type RoadmapModel = ReturnType<typeof useRoadmap>;
