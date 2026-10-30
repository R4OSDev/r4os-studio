export type GitHubIssueState='open'|'closed'|'all';
export interface GitHubIssue {
  number:number;title:string;state:'open'|'closed';url:string;updatedAt:string;
  labels:{name:string;color:string}[];moreLabels:number;
}
export interface GitHubIssuePage {
  scope:{projectId:string;repositoryId:number;bindingRevision:number;credentialRevision:number};
  repository:string;state:GitHubIssueState;items:GitHubIssue[];openCount:number;
  nextCursor:string|null;checkedAt:string;expiresAt:string;cached:boolean;
}
