export type AgentToolId = 'studio.exec_command' | 'studio.write_stdin' | 'studio.terminate_process'
  | 'studio.read_attachment' | 'studio.list_generated_images' | 'studio.import_generated_image'
  | 'studio.list_directory' | 'studio.read_file' | 'studio.search' | 'studio.write_file'
  | 'studio.apply_patch' | 'studio.create_directory'
  | 'studio.validate_skill' | 'studio.save_skill'
  | 'studio.push_project'
  | 'studio.get_remote_host' | 'studio.run_remote_command' | 'studio.remote_files' | 'studio.read_remote_job' | 'studio.stop_remote_job'
  | 'studio.build_project' | 'studio.deploy_project' | 'studio.run_project' | 'studio.read_development_job'
  | 'studio.stop_development_job' | 'studio.complete_development_job' | 'studio.capture_vm' | 'studio.send_vm_input' | 'studio.start_project_vm'
  | 'studio.read_update_package' | 'studio.plan_update_package' | 'studio.build_update_package' | 'studio.check_update_vm'
  | 'studio.upload_update_package' | 'studio.install_update_package' | 'studio.commit_update' | 'studio.verify_update'
  | 'studio.resume_update' | 'studio.abort_update' | 'studio.rollback_update' | 'studio.cleanup_update_transport';
export type ToolPermissions = Record<AgentToolId, boolean>;
export type SessionOwner = { type: 'project'; id: string } | { type: 'skill'; id: string };
export type RunState = 'queued' | 'starting' | 'running' | 'stopping' | 'completed' | 'failed' | 'interrupted' | 'unknown';
export interface AgentRun { id: string; sessionId: string; owner?: SessionOwner; mode?: 'goal'; state: RunState; error: string | null; createdAt: string; completedAt: string | null; threadId?: string | null; turnId?: string | null; messageSupport?: boolean; goalControlSupport?: boolean; goalActivation?: { requestId: string; state: 'pending' | 'confirmed' | 'failed' | 'unknown' } }
export interface AgentSession {
  id: string; owner: SessionOwner; projectId?: string; skillId?: string; name: string; providerId: string; model: string; effort: string; fastMode: boolean;
  permissions: ToolPermissions; engine: { profile: string; version: string; sha256: string; available?: boolean;
    api?: { providerId: string; baseUrl: string; protocol: 'responses' | 'chat-completions' } };
  webSearchEnabled?: boolean;
  environmentNotesEnabled?: boolean;
  imageGenerationEnabled?: boolean;
  roadmapEnabled?: boolean;
  environmentNotesAccess?: { available: boolean; reason?: string };
  roadmapAccess?: { available: boolean; reason?: string };
  remoteHostAccess?: { available: boolean; assignedId?: string | null; hostName?: string; reason?: string };
  revision: number; createdAt: string; updatedAt: string; latestRun: AgentRun | null;
  skillOverrides: Record<string, boolean>;
}
export interface SessionCreate { name: string; providerId: string; model: string; effort: string; fastMode?: boolean; requestId: string }
export interface SessionUpdate {
  revision: number; name?: string; providerId?: string; model?: string; effort?: string; fastMode?: boolean; permissions?: ToolPermissions;
  webSearchEnabled?: boolean;
  environmentNotesEnabled?: boolean;
  imageGenerationEnabled?: boolean;
  roadmapEnabled?: boolean;
  skillOverrides?: Record<string, boolean>;
}
export interface SessionOptions {
  skills?: { id: string; name: string; description: string; available: boolean; reason?: string }[];
  development?: import('./project-development.js').DevelopmentOptions;
  providers: { id: string; name: string; models: { id: string; name: string; efforts: string[]; defaultEffort: string; fastModeAvailable: boolean; imageInputs?: 'supported' | 'unsupported' | 'unknown'; inputModalities?: ('text' | 'image' | 'audio')[] | null }[] }[];
  tools: { id: AgentToolId; defaultEnabled: boolean }[];
  nativeTools?: { id: 'web_search' | 'image_generation'; defaultEnabled: boolean }[];
  engine: { profile: string; version: string; sha256: string; available: boolean; reason?: string };
}
export interface SessionItem {
  generatedImage?: import('./generated-images.js').GeneratedImage;
  generatedAsset?: import('./generated-images.js').GeneratedAsset;
  attachments?: import('./agent-inputs.js').FrozenAttachment[];
  id: string; runId: string; turnId?: string; type: string; text?: string; tool?: string; status?: string;
  arguments?: unknown; output?: string; error?: string; exitCode?: number; [key: string]: unknown;
  developmentStop?: import('./project-development.js').DevelopmentStopReceipt;
  roadmap?: { operation: string; code?: number; workflowId?: string; phase?: string; revision?: number; currentVersionId?: string; requestId?: string; versionId?: string; sha256?: string };
  remote?: RemoteReceiptSummary;
  webSearch?: { action: 'search' | 'openPage' | 'findInPage' | 'other'; queries?: string[]; url?: string; pattern?: string; sources?: { title: string; url: string }[]; truncated?: boolean };
}
export interface SessionHistory { items: SessionItem[]; before: number | null; cursor: number }
export interface SessionDeletionPreview { sessionId: string; name: string; revision: number; scopeHash: string; allowed: boolean; blockers: string[] }
export interface SessionDeletionInput { requestId: string; revision: number; scopeHash: string; confirmName: string }
export interface SessionDeletionReceipt { requestId: string; sessionId: string; state: 'deleting' | 'unknown' | 'deleted'; phase: string; reason?: string; creationRequestIds?: string[] }
export interface AgentEvent { seq: number; kind: string; runId: string | null; payload: unknown }
export interface RemoteReceiptSummary {
  id?: string; requestId?: string; hostId?: string; hostName?: string; operation?: string;
  state?: string; phase?: string; deadlineAt?: string; code?: number; stopRequested?: boolean;
  binding?: { id: string; endpointRevision: number; credentialRevision: number; trustRevision: number };
  localClientEndConfirmed?: boolean; remoteProcessEndConfirmed?: boolean; commandReturnConfirmed?: boolean; commandExitCode?: number | null;
}

export interface NativeImageCapability { schema: 1; providerId?: string; model?: string; engine?: AgentSession['engine']; checkedAt?: string; state: 'available' | 'unavailable' | 'unknown'; available: boolean; qualified: boolean; reason: string; accountType?: string; accountPlan?: string; accountSha256?: string; inputModalities?: ('text' | 'image' | 'audio')[] | null; policySha256?: string }
