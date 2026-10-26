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
