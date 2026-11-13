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
  completedAt?: string | null;
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
  completedAt?: string | null;
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
export interface RoadmapBinding { sourceGeneration?: string; revision: number; currentVersionId: string }
export interface RoadmapPage<T = RoadmapRecord> extends RoadmapBinding { items: T[]; nextCursor: string | null }
export interface RoadmapRead<T = RoadmapRecord> extends RoadmapBinding { entity: T }
export type RoadmapOverview = { exists: false; projectId: string }
  | { exists: true; sourceGeneration?: string; roadmap: RoadmapHeader; versions: RoadmapPage<RoadmapVersionHeader> };
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
export interface RoadmapExport extends RoadmapBinding {
  format?:'json'; scope?:'roadmap'|'version'|'subversion';targetId?:string;schemaVersion?:1;storedTreeComplete?:true;archivedTreesIncluded?:false;
  id: string;
  projectId: string;
  roadmapId: string;
  versionId: string;
  number: string;
  filename: string;
  encoding: 'utf-8';
  byteLength: number;
  sha256: string;
  createdAt: string;
}
export interface RoadmapExportInput {
  requestId: string;
  versionId: string;
  expectedRevision: number;
  currentVersionId: string;
}

export type RoadmapWorkflowPhase = 'preparing' | 'archiving' | 'archive_ready' | 'documents_verified' | 'complete' | 'cancelled' | 'aborted';
export interface RoadmapDocumentReceipt { path: string; expectedSha256: string | null; sha256: string; byteLength: number }
export interface RoadmapWorkflow extends RoadmapBinding {
  workflowId: string; phase: RoadmapWorkflowPhase; versionId: string; number: string;
  sourceBinding: RoadmapBinding;
  archive: { path: string; sha256: string; byteLength: number; exportId: string; encoding: 'utf-8' } | null;
  documents: RoadmapDocumentReceipt[]; documentCount: number; documentationSummary: string | null;
  baselineFileCount: number; attemptCount: number; createdAt: string; updatedAt: string;
  capabilities: { prepare: boolean; status: boolean; cancel: boolean; finalize: boolean };
  nextVersionId?: string; nextNumber?: string; completedAt?: string;
}
export type RoadmapWorkflowSummary = Omit<RoadmapWorkflow, 'documents'> & { summaryTruncated: boolean };
export interface RoadmapWorkflowPage { items: RoadmapWorkflowSummary[]; nextCursor: string | null }

/** Target IDs and reorder input.ids may use $key for an earlier batch create. */
export type RoadmapBatchOperation = Pick<RoadmapMutation,'target'|'action'|'input'> & {key?:string};
export interface RoadmapBatch {requestId:string;expectedRevision:number;currentVersionId:string;operations:RoadmapBatchOperation[]}
export interface RoadmapBatchResult extends RoadmapBinding {requestId:string;operations:{index:number;key?:string;entity:RoadmapMutationResult['entity']}[];references:Record<string,string>}

export type RoadmapJsonInput = {requestId:string;expectedRevision:number;currentVersionId:string} & ({scope:'roadmap'}|{scope:'version';versionId:string}|{scope:'subversion';versionId:string;subversionId:string});
export interface RoadmapJsonDocument {schema:'r4os-studio-roadmap';schemaVersion:1;scope:'roadmap'|'version'|'subversion';source:{projectId:string;roadmapId:string;revision:number;currentVersionId:string;exportId:string;createdAt:string};completeness:{storedTreeComplete:true;archivedTreesIncluded:false};archiveReferences:unknown[];data:ProjectRoadmap|RoadmapVersion|RoadmapSubversion}

export interface RoadmapImportPreview extends RoadmapBinding {
 previewId:string;projectId:string;sha256:string;byteLength:number;scope:'roadmap'|'version'|'subversion';mode:'add'|'update';
 source:{id:string;sha256:string;byteLength:number;scope:string};counts:{create:number;update:number;delete:0};conflicts:string[];conflictCount:number;canApply:boolean;matching:string;currentVersionChanged:false;archiveReferencesIgnored:number;
 changes:{kind:string;sourceId:string;targetId:string;action:string;fields:string[]}[];
 mapping:{kind:string;sourceId:string;targetId:string;action:string;sourceNumber?:string;targetNumber?:string;previousNumber?:string;sourceOrder?:number;targetOrder?:number}[];totalChanges:number;detailsTruncated:boolean;
}
export interface RoadmapImportApply {requestId:string;previewId:string;previewSha256:string;expectedRevision:number;currentVersionId:string;confirm:true}
export interface RoadmapImportResult extends RoadmapBinding {requestId:string;previewId:string;confirmed:true;counts:{create:number;update:number;delete:0};currentVersionChanged:false}
