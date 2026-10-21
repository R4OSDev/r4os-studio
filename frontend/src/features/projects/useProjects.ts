import { useEffect, useState } from 'react';
import type { ProjectSummary, ProjectsResponse } from '../../../../shared/projects';

export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch('/api/projects', { cache: 'no-store', signal: controller.signal });
        if (!response.ok) throw new Error('Projects could not be loaded.');
        const result = await response.json() as ProjectsResponse;
        if (!controller.signal.aborted) setProjects(result.projects);
      } catch {
        if (!controller.signal.aborted) setError('Projects could not be loaded.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  return { projects, loading, error };
}
