import type { RoadmapMutation, RoadmapMutationResult, RoadmapOverview, RoadmapPage, RoadmapRead, RoadmapVersionHeader } from '../../../../shared/project-roadmaps';
import { projectRequest } from '../projects/api';

export function roadmapRequest<T>(id: string, path = '', token = '', method = 'GET', body?: unknown, signal?: AbortSignal) {
  return projectRequest<T>(`/${id}/roadmap${path}`, token, method, body, signal);
}
export const overview = (id: string, signal?: AbortSignal) => roadmapRequest<RoadmapOverview>(id, '', '', 'GET', undefined, signal);
export const version = (id: string, versionId: string, signal?: AbortSignal) => roadmapRequest<RoadmapRead<RoadmapVersionHeader>>(id, `/versions/${versionId}`, '', 'GET', undefined, signal);
export const versionPage = (id: string, cursor: string, signal?: AbortSignal) => roadmapRequest<RoadmapPage<RoadmapVersionHeader>>(id, '/versions?cursor=' + encodeURIComponent(cursor), '', 'GET', undefined, signal);
export const mutate = (id: string, token: string, body: RoadmapMutation) => roadmapRequest<RoadmapMutationResult>(id, '/mutations', token, 'POST', body);
