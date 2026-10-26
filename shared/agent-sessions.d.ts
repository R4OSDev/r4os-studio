export type AgentToolId = 'studio.exec_command' | 'studio.write_stdin' | 'studio.terminate_process'
  | 'studio.list_directory' | 'studio.read_file' | 'studio.search' | 'studio.write_file'
  | 'studio.apply_patch' | 'studio.create_directory'
  | 'studio.validate_skill' | 'studio.save_skill'
  | 'studio.build_project' | 'studio.deploy_project' | 'studio.run_project' | 'studio.read_development_job'
  | 'studio.stop_development_job' | 'studio.complete_development_job' | 'studio.capture_vm' | 'studio.send_vm_input' | 'studio.start_project_vm';
export type ToolPermissions = Record<AgentToolId, boolean>;
export type SessionOwner = { type: 'project'; id: string } | { type: 'skill'; id: string };
export type RunState = 'queued' | 'starting' | 'running' | 'stopping' | 'completed' | 'failed' | 'interrupted' | 'unknown';
export interface AgentRun { id: string; sessionId: string; owner?: SessionOwner; state: RunState; error: string | null; createdAt: string; completedAt: string | null }
export interface AgentSession {
  id: string; owner: SessionOwner; projectId?: string; skillId?: string; name: string; providerId: string; model: string; effort: string; fastMode: boolean;
  permissions: ToolPermissions; engine: { profile: string; version: string; sha256: string; available?: boolean };
  revision: number; createdAt: string; updatedAt: string; latestRun: AgentRun | null;
  skillOverrides: Record<string, boolean>;
}
export interface SessionCreate { name: string; providerId: string; model: string; effort: string; fastMode?: boolean; requestId: string }
export interface SessionUpdate {
  revision: number; name?: string; providerId?: string; model?: string; effort?: string; fastMode?: boolean; permissions?: ToolPermissions;
  skillOverrides?: Record<string, boolean>;
}
export interface SessionOptions {
  skills?: { id: string; name: string; description: string; available: boolean; reason?: string }[];
  development?: import('./project-development.js').DevelopmentOptions;
  providers: { id: string; name: string; models: { id: string; name: string; efforts: string[]; defaultEffort: string; fastModeAvailable: boolean }[] }[];
  tools: { id: AgentToolId; defaultEnabled: boolean }[];
  engine: { profile: string; version: string; sha256: string; available: boolean; reason?: string };
}
export interface SessionItem {
  id: string; runId: string; type: string; text?: string; tool?: string; status?: string;
  arguments?: unknown; output?: string; error?: string; exitCode?: number; [key: string]: unknown;
}
export interface SessionHistory { items: SessionItem[]; before: number | null; cursor: number }
export interface AgentEvent { seq: number; kind: string; runId: string | null; payload: unknown }
