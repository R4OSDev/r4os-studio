export interface GitHubConnection {
  id: string;
  name: string;
  revision: number;
  hasToken: boolean;
  createdAt: string;
  updatedAt: string;
}
export interface GitHubConnectionList { connections: GitHubConnection[]; csrfToken: string }
export interface GitHubConnectionInput { id: string; name: string; token: string }
export interface GitHubConnectionChange { revision: number; name: string; token?: string }
