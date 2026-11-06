import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { RoadmapBinding, RoadmapOverview, RoadmapVersionHeader } from '../../../../shared/project-roadmaps';
import { ProjectRequestError } from '../projects/api';
import * as api from './api';

interface State { key: string; scope: string; epoch: number; overview: RoadmapOverview | null; version: RoadmapVersionHeader | null; error: string }
export function useRoadmap(id: string | null, versionId?: string) {
  const [epoch, setEpoch] = useState(0), scope = `${id}:${versionId ?? ''}`, key = `${scope}:${epoch}`;
  const [state, setState] = useState<State>({ key: '', scope: '', epoch: 0, overview: null, version: null, error: '' });
  const latest = useRef(state);
  useLayoutEffect(() => { latest.current = state; });
  const [paging, setPaging] = useState(false), [changedKey, setChangedKey] = useState('');
  const [verification, setVerification] = useState({ key: '', error: '' });
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController(), signal = controller.signal;
    const previous = latest.current;
    const known = previous.scope.startsWith(id + ':') && previous.overview?.exists;
    void (async () => {
      try {
        // A cold uninitialized project has no version binding yet. Once this
        // project's existence is known, independent initial reads can overlap.
        const detail = known && versionId ? api.version(id, versionId, signal).then(value => ({ value }), error => ({ error: error as Error })) : null;
        const overview = await api.overview(id, signal);
        if (overview.exists ? overview.roadmap.projectId !== id : overview.projectId !== id) throw new Error('The roadmap belongs to another project.');
        let version: RoadmapVersionHeader | null = null, error = '';
        if (overview.exists && versionId) {
          try {
            const read = detail ? await detail : { value: await api.version(id, versionId, signal) };
            if ('error' in read) throw read.error;
            if (read.value.entity.id !== versionId || read.value.revision !== overview.roadmap.revision || read.value.currentVersionId !== overview.roadmap.currentVersionId || read.value.sourceGeneration !== overview.sourceGeneration)
              throw new Error('The roadmap changed while loading. Refresh before continuing.');
            version = read.value.entity;
          } catch (cause) { error = (cause as Error).message; }
        }
        if (!signal.aborted) setState({ key, scope, epoch, overview, version, error });
      } catch (cause) {
        if (!signal.aborted) setState(old => ({ key, scope, epoch, overview: old.scope === scope ? old.overview : null,
          version: old.scope === scope ? old.version : null, error: (cause as Error).message }));
      }
    })();
    return () => controller.abort();
  }, [id, versionId, epoch, scope, key]);
  const reload = useCallback(() => setEpoch(value => value + 1), []);
  const active = state.scope === scope ? state : { key, scope, epoch, overview: null, version: null, error: '' };
  const revision = active.overview?.exists ? active.overview.roadmap.revision : null;
  const currentVersionId = active.overview?.exists ? active.overview.roadmap.currentVersionId : null;
  const sourceGeneration = active.overview?.exists ? active.overview.sourceGeneration : undefined;
  const observation = `${key}:${revision}:${currentVersionId}:${sourceGeneration ?? ''}`;
  useEffect(() => {
    if (!id || state.key !== key) return;
    const controller = new AbortController(); let pending = false;
    const timer = window.setInterval(() => {
      if (document.hidden || pending) return;
      pending = true;
      void api.roadmapRequest<RoadmapBinding>(id, '/revision', '', 'GET', undefined, controller.signal).then(value => {
        if (controller.signal.aborted) return;
        setVerification(old => old.key === key && !old.error ? old : { key, error: '' });
        if (value.revision !== revision || value.currentVersionId !== currentVersionId || value.sourceGeneration !== sourceGeneration) setChangedKey(observation);
      }).catch((cause: Error) => {
        if (controller.signal.aborted) return;
        if (cause instanceof ProjectRequestError && cause.status === 404 && revision === null) return;
        setVerification({ key, error: cause.message || 'The saved roadmap could not be verified. Existing input was preserved.' });
      }).finally(() => { pending = false; });
    }, 5000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [id, key, state.key, revision, currentVersionId, sourceGeneration, observation]);
  async function more() {
    if (!id || paging || !active.overview?.exists || !active.overview.versions.nextCursor) return;
    const cursor = active.overview.versions.nextCursor;
    setPaging(true);
    try {
      const page = await api.versionPage(id, cursor);
      setState(previous => {
        if (previous.key !== key || !previous.overview?.exists) return previous;
        if (page.revision !== previous.overview.roadmap.revision || page.currentVersionId !== previous.overview.roadmap.currentVersionId || page.sourceGeneration !== previous.overview.sourceGeneration)
          return { ...previous, error: 'The roadmap changed. Refresh before continuing.' };
        return { ...previous, overview: { ...previous.overview, versions: { ...page, items: [...previous.overview.versions.items, ...page.items] } } };
      });
    } catch (cause) { setState(previous => previous.key === key ? { ...previous, error: (cause as Error).message } : previous); }
    finally { setPaging(false); }
  }
  return { ...active, error: active.error || (verification.key === key ? verification.error : ''), loading: !!id && state.key !== key,
    paging, more, reload, epoch: active.epoch, sourceGeneration, remoteChanged: changedKey === observation };
}
export type RoadmapModel = ReturnType<typeof useRoadmap>;
