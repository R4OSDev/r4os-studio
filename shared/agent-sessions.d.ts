export type AgentToolId = 'studio.exec_command' | 'studio.write_stdin' | 'studio.terminate_process'
  | 'studio.list_directory' | 'studio.read_file' | 'studio.search' | 'studio.write_file'
  | 'studio.apply_patch' | 'studio.create_directory';
export type ToolPermissions = Record<AgentToolId, boolean>;
export type RunState = 'queued' | 'starting' | 'running' | 'stopping' | 'completed' | 'failed' | 'interrupted' | 'unknown';
export interface AgentRun { id: string; sessionId: string; state: RunState; error: string | null; createdAt: string; completedAt: string | null }
export interface AgentSession {
  id: string; projectId: string; name: string; providerId: string; model: string; effort: string;
  permissions: ToolPermissions; engine: { profile: string; version: string; sha256: string; available?: boolean };
  revision: number; createdAt: string; updatedAt: string; latestRun: AgentRun | null;
}
export interface SessionCreate { name: string; providerId: string; model: string; effort: string; requestId: string }
export interface SessionUpdate {
  revision: number; name?: string; providerId?: string; model?: string; effort?: string; permissions?: ToolPermissions;
}
export interface SessionOptions {
  providers: { id: string; name: string; models: { id: string; name: string; efforts: string[]; defaultEffort: string }[] }[];
  tools: { id: AgentToolId; defaultEnabled: boolean }[];
  engine: { profile: string; version: string; sha256: string; available: boolean; reason?: string };
}
export interface SessionItem {
  id: string; runId: string; type: string; text?: string; tool?: string; status?: string;
  arguments?: unknown; output?: string; error?: string; exitCode?: number; [key: string]: unknown;
}
export interface SessionHistory { items: SessionItem[]; before: number | null; cursor: number }
export interface AgentEvent { seq: number; kind: string; runId: string | null; payload: unknown }
