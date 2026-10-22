import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProjectSummary, ProjectsResponse } from '../../../../shared/projects';
import { projectRequest } from './api';

export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [token, setToken] = useState('');
  const active = useRef(true);
  const request = useRef<AbortController | null>(null);

  const reload = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const result = await projectRequest<ProjectsResponse>('', '', 'GET', undefined, controller.signal);
      if (active.current && !controller.signal.aborted) { setProjects(result.projects); setToken(result.csrfToken); setError(''); }
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
  return { projects, loading, error, token, reload, remember, forget };
}
