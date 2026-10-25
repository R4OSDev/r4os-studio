export interface GitHubConnection {
  id: string;
  name: string;
  revision: number;
  hasToken: boolean;
  createdAt: string;
  updatedAt: string;
  tokenRevision: number;
  lastTest?: GitHubTestResult;
}
export type GitHubTestStatus = 'success' | 'authentication_failed' | 'forbidden' | 'rate_limited' | 'network_error' | 'timeout' | 'server_error' | 'invalid_response';
export interface GitHubTestResult { status: GitHubTestStatus; checkedAt: string; login?: string; userId?: number }
export interface GitHubConnectionList { connections: GitHubConnection[]; csrfToken: string }
export interface GitHubConnectionInput { id: string; name: string; token: string }
export interface GitHubConnectionChange { revision: number; name: string; token?: string }
