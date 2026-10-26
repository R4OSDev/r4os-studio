export interface GitHubAccount {
  connectionId: string; connectionName: string; tokenRevision: number;
  login: string; userId: number; checkedAt: string;
  create: 'unverified';
}
export interface GitHubRepository {
  id: number; owner: string; name: string; fullName: string; url: string;
  private: boolean; defaultBranch: string | null; archived: boolean;
  read: boolean; push: boolean;
}
export interface GitHubBranch { name: string; sha: string; protected: boolean }
export interface GitHubProjectBinding {
  schema: 1; revision: number; connectionId: string; userId: number;
  repository: GitHubRepository; branch: string;
  author: { name: string; email: string };
}
export interface GitHubProjectReference { id: string; name: string }
export interface GitHubRepositoryPage { account: GitHubAccount; repositories: GitHubRepository[]; page: number; hasMore: boolean }
export interface GitHubBranchPage { account: GitHubAccount; repository: GitHubRepository; branches: GitHubBranch[]; page: number; hasMore: boolean }
export interface GitHubProjectStatus {
  binding: GitHubProjectBinding | null; head: string | null; remoteHead: string | null;
  ahead: number; behind: number; state: string; snapshot: string;
  changes: { path: string; status: string }[]; checkedAt: string | null;
}
export interface GitHubJob {
  id: string; projectId: string; kind: string; state: 'queued' | 'running' | 'completed' | 'failed' | 'unknown';
  phase: string; createdAt: string; updatedAt: string; error?: string; code?: number;
  result?: { binding?: GitHubProjectBinding; initialized?: boolean } | GitHubProjectStatus;
}
