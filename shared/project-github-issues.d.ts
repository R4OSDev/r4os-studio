import type { RoadmapIssueLink } from './project-roadmaps';
export type GitHubIssueState='open'|'closed'|'all';
export interface GitHubIssue {
  number:number;title:string;state:'open'|'closed';url:string;updatedAt:string;
  id?: string;
  labels:{name:string;color:string}[];moreLabels:number;
  roadmap?: RoadmapIssueLink;
}
export interface GitHubIssuePage {
  scope:{projectId:string;repositoryId:number;bindingRevision:number;credentialRevision:number};
  repository:string;state:GitHubIssueState;items:GitHubIssue[];openCount:number;
  nextCursor:string|null;checkedAt:string;expiresAt:string;cached:boolean;
  stale?:boolean;refreshError?:string;
}
export interface GitHubIssueCount {
  count: number | null;
  checkedAt: string | null;
  state: 'current' | 'stale' | 'unknown' | 'unavailable';
}
export interface GitHubIssueOutcome {
  requestId: string;
  issueId: string;
  repositoryId: number;
  number: number;
  url: string;
  state: 'ready' | 'comment_pending' | 'commented' | 'close_pending' | 'closed' | 'complete';
  reason: 'COMPLETED' | 'NOT_PLANNED';
  comment?: { id: string; url: string };
  closedAt?: string;
  subversionId?: string | null;
  syncError?: string;
}
