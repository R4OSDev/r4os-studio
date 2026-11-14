import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProjectGrouping, ProjectSummary, ProjectsResponse } from '../../../../shared/projects';
import { projectRequest, ProjectRequestError } from './api';

const emptyGrouping: ProjectGrouping = { groups: [], memberships: {} };

export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [grouping, setGrouping] = useState(emptyGrouping);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [token, setToken] = useState('');
  const active = useRef(true);
  const request = useRef<AbortController | null>(null);
  const groupingEpoch = useRef(0);

  const reload = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const epoch = groupingEpoch.current;
    try {
      const result = await projectRequest<ProjectsResponse>('', '', 'GET', undefined, controller.signal);
      if (active.current && !controller.signal.aborted) {
        setProjects(result.projects); setToken(result.csrfToken); setError('');
        if (epoch === groupingEpoch.current) setGrouping(result.grouping ?? emptyGrouping);
      }
    } catch {
      if (active.current && !controller.signal.aborted) setError('Projects could not be loaded.');
    } finally { if (active.current && !controller.signal.aborted) setLoading(false); }
  }, []);

  useEffect(() => {
    active.current = true;
    const initial = window.setTimeout(() => void reload(), 0);
    return () => { active.current = false; window.clearTimeout(initial); request.current?.abort(); };
  }, [reload]);

  const remember = useCallback((project: ProjectSummary) => setProjects((previous) =>
    [...previous.filter((value) => value.id !== project.id), project].sort((a, b) => a.name.localeCompare(b.name, 'en', { numeric: true }))), []);
  const forget = useCallback((id: string) => setProjects((previous) => previous.filter((project) => project.id !== id)), []);

  async function changeGrouping(path: string, method: string, body: unknown) {
    try {
      const changed = await projectRequest<ProjectGrouping>(path, token, method, body);
      if (active.current) {
        groupingEpoch.current++;
        setGrouping(changed);
      }
    } catch (cause) {
      if (cause instanceof ProjectRequestError && [403, 404, 409].includes(cause.status)) void reload();
      throw cause;
    }
  }

  return { projects, grouping, changeGrouping, loading, error, token, reload, remember, forget };
}
