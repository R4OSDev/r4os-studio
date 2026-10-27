export type RoadmapVersionStatus = 'open' | 'complete' | 'discarded';
export type RoadmapItemStatus = 'open' | 'done' | 'discarded';

export interface RoadmapEntity {
  id: string;
  notes: string;
  revision: number;
  createdAt: string;
  updatedAt: string;
}
export interface RoadmapItem extends RoadmapEntity {
  subversionId: string;
  description: string;
  status: RoadmapItemStatus;
  order: number;
}
export interface RoadmapSubversion extends RoadmapEntity {
  versionId: string;
  number: string;
  title: string;
  description: string;
  status: RoadmapVersionStatus;
  order: number;
  tasks: RoadmapItem[];
  acceptances: RoadmapItem[];
}
export interface RoadmapVersion extends RoadmapEntity {
  number: string;
  title: string;
  vision: string;
  status: RoadmapVersionStatus;
  order: number;
  subversions: RoadmapSubversion[];
}
export interface ProjectRoadmap extends RoadmapEntity {
  projectId: string;
  description: string;
  currentVersionId: string;
  versions: RoadmapVersion[];
}
export type ProjectRoadmapState = { exists: false; projectId: string }
  | { exists: true; roadmap: ProjectRoadmap };
