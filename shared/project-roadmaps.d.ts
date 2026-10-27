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

export interface RoadmapProgress {
  tasks: { total: number; open: number; done: number; discarded: number };
  acceptances: { total: number; open: number; done: number; discarded: number };
}
export type RoadmapHeader = Omit<ProjectRoadmap, 'versions'> & { progress: RoadmapProgress };
export type RoadmapVersionHeader = Omit<RoadmapVersion, 'subversions'> & { subversionCount: number; progress: RoadmapProgress };
export type RoadmapSubversionHeader = Omit<RoadmapSubversion, 'tasks' | 'acceptances'> & { progress: RoadmapProgress };
export type RoadmapRecord = RoadmapHeader | RoadmapVersionHeader | RoadmapSubversionHeader | RoadmapItem;
export type RoadmapTarget = { kind: 'roadmap' | 'version'; id?: string }
  | { kind: 'subversion'; id?: string; versionId: string }
  | { kind: 'task' | 'acceptance'; id?: string; versionId: string; subversionId: string };
export interface RoadmapBinding { revision: number; currentVersionId: string }
export interface RoadmapPage<T = RoadmapRecord> extends RoadmapBinding { items: T[]; nextCursor: string | null }
export interface RoadmapRead<T = RoadmapRecord> extends RoadmapBinding { entity: T }
export type RoadmapOverview = { exists: false; projectId: string }
  | { exists: true; roadmap: RoadmapHeader; versions: RoadmapPage<RoadmapVersionHeader> };
export interface RoadmapMutation {
  requestId: string;
  expectedRevision: number;
  currentVersionId: string;
  target: RoadmapTarget;
  action: 'create' | 'update' | 'append_notes' | 'replace_notes' | 'reorder' | 'delete' | 'set_current';
  input?: { number?: string; title?: string; description?: string; vision?: string; notes?: string;
    status?: RoadmapVersionStatus | RoadmapItemStatus; ids?: string[]; confirm?: true };
}
export interface RoadmapMutationResult extends RoadmapBinding {
  entity: RoadmapRecord | { id: string; kind: RoadmapTarget['kind']; deleted: true }
    | { kind: RoadmapTarget['kind']; ids: string[] };
}
