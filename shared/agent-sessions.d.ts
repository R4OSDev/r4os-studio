export type AgentToolId = 'studio.skill_discover' | 'studio.skill_call' | 'studio.read_skill_result'
  | 'studio.exec_command' | 'studio.write_stdin' | 'studio.terminate_process'
  | 'studio.generate_image' | 'studio.read_context_result' | 'studio.read_attachment' | 'studio.list_generated_images' | 'studio.import_generated_image'
  | 'studio.list_directory' | 'studio.read_file' | 'studio.search' | 'studio.write_file'
  | 'studio.apply_patch' | 'studio.create_directory'
  | 'studio.validate_skill' | 'studio.save_skill'
  | 'studio.push_project' | 'studio.read_project_git'
  | 'studio.get_remote_host' | 'studio.run_remote_command' | 'studio.remote_files' | 'studio.read_remote_job' | 'studio.stop_remote_job'
  | 'studio.build_project' | 'studio.deploy_project' | 'studio.run_project' | 'studio.read_development_job'
  | 'studio.stop_development_job' | 'studio.complete_development_job' | 'studio.capture_vm' | 'studio.send_vm_input' | 'studio.start_project_vm' | 'studio.stop_project_vm' | 'studio.restart_project_vm' | 'studio.run_vm_command' | 'studio.control_app_window'
  | 'studio.read_update_package' | 'studio.plan_update_package' | 'studio.build_update_package' | 'studio.check_update_vm'
  | 'studio.upload_update_package' | 'studio.install_update_package' | 'studio.commit_update' | 'studio.verify_update'
  | 'studio.resume_update' | 'studio.abort_update' | 'studio.rollback_update' | 'studio.cleanup_update_transport';
export type ToolPermissions = Record<AgentToolId, boolean>;
export type SessionOwner = { type: 'project'; id: string } | { type: 'skill'; id: string };
export type RunState = 'queued' | 'starting' | 'running' | 'stopping' | 'completed' | 'failed' | 'interrupted' | 'unknown';
export interface ProviderRetry { state: 'waiting' | 'submitting' | 'continuing' | 'completed' | 'cancelled' | 'exhausted' | 'unknown'; sequence: number; attempt: number; maxAttempts: number; nextAttempt: number; remainingMs: number; error: string; httpStatusCode: number | null; sampledAt: string }
export interface AgentRun { engine?: { version?: string; sha256?: string }; selection?: ModelChoice & {providerId:string}; id: string; sessionId: string; owner?: SessionOwner; mode?: 'goal'; state: RunState; error: string | null; createdAt: string; completedAt: string | null; threadId?: string | null; turnId?: string | null; messageSupport?: boolean; messageWaitTarget?: import('./agent-messages.js').AfterResponseTarget; goalControlSupport?: boolean; goalActivation?: { requestId: string; state: 'pending' | 'confirmed' | 'failed' | 'unknown' }; providerRetry?: ProviderRetry }
export interface ModelChoice { model:string; effort:string; fastMode:boolean }
export interface ContextLimitPreference { mode: 'off' | 'global' | 'on'; budgetTokens: number | null }
export interface ContextLimitDefaults { revision: number; enabled: boolean; budgetTokens: number; defaultEnabled: boolean; defaultBudgetTokens: number; maxBudgetTokens: number }
export interface ModelChoiceInput extends ModelChoice { requestId:string; revision:number; selectionRevision:number; afterRunId:string }
export interface PendingModelChoice { revision:number; requestId:string; afterRunId:string; state:'pending'|'blocked'; choice:ModelChoice; reason:string|null; updatedAt:string }
export interface ModelChoiceReceipt { requestId:string; sessionId:string; selectionRevision:number; afterRunId:string; state:'pending'|'cancelled'; choice:ModelChoice; acceptedAt:string }
export interface ModelChoiceResult { receipt:ModelChoiceReceipt; session:AgentSession }
export interface QuotaWaitCancelInput { requestId: string; waitId: string; revision: number }
export interface QuotaWaitResult { session?: AgentSession; owner: SessionOwner; sessionId: string; quotaWait: SessionQuotaWait; receipt: { requestId: string; waitId: string; sessionId: string; state: 'confirmed'; outcome: 'cancelled' | 'already-admitted' | 'already-ended' } }
export interface SessionQuotaWait {
  schema?: 1; owner?: SessionOwner; sessionId?: string;
  revision: number; state: 'idle' | 'waiting' | 'dispatching' | 'resumed' | 'cancelled' | 'unknown'; active: boolean; waitId: string | null;
  sourceRunId?: string; providerId?: string; model?: string; reason?: string; createdAt?: string; negativeAt?: string; resetAt?: string | null; resumedRunId?: string;
  observation?: { state: string; checkedAt?: string | null; nextCheckAt?: string | null; reason?: string | null; windows?: { id: string; label: string; remaining: number | null; resetAt: string | null }[] };
}
export interface AgentSession {
  contextLimit?: ContextLimitPreference;
  quotaWait?: SessionQuotaWait;
  context?: SessionContext;
  id: string; owner: SessionOwner; projectId?: string; skillId?: string; name: string; providerId: string; model: string; effort: string; fastMode: boolean;
  permissions: ToolPermissions; engine: { kind?: 'claude-code' | 'studio'; toolScope?: 'project' | 'skill'; profile?: string; version: string; sha256: string; available?: boolean; reason?: string;
    api?: { providerId: string; kind?: import('./api-providers.js').ApiProviderKind; baseUrl: string; protocol: import('./api-providers.js').ApiProtocol; server?: 'custom' | 'ollama' | 'lm-studio' } };
  webSearchEnabled?: boolean;
  environmentNotesEnabled?: boolean;
  imageGenerationEnabled?: boolean;
  roadmapEnabled?: boolean;
  environmentNotesAccess?: { available: boolean; reason?: string };
  roadmapAccess?: { available: boolean; reason?: string };
  remoteHostAccess?: { available: boolean; assignedId?: string | null; hostName?: string; reason?: string };
  revision: number; createdAt: string; updatedAt: string; latestRun: AgentRun | null;
  skillOverrides: Record<string, boolean>;
  selectionRevision?:number;
  selectionStateRevision?:number;
  pendingModel?:PendingModelChoice|null;
}
export type AgentSessionSummary = Pick<AgentSession, 'id' | 'owner' | 'projectId' | 'skillId' | 'name' | 'revision' | 'createdAt' | 'updatedAt'> & {
  latestRun: Pick<AgentRun, 'id' | 'state'> | null;
};
export interface SessionContext {
  schema: 1; revision: number; owner: SessionOwner; sessionId: string;
  state: 'available' | 'pending' | 'stale' | 'unavailable' | 'blocked'; reason: string;
  engine: 'codex' | 'claude-code' | 'studio'; engineVersion: string; engineSha256: string;
  providerId: string; requestedModel: string; model: string | null; modelProvider: string | null;
  threadId: string | null; runId: string | null; turnId: string | null;
  source: string | null; reportedAt: string | null;
  usedTokens: number | null; capacityTokens: number | null; remainingTokens: number | null;
  overflowTokens: number | null; usedRatio: number | null;
  last: Record<string, number | null> | null;
  autoCompactThreshold: number | null; nominalModelCapacity: null;
  estimatedInputTokens?: number | null; estimateMethod?: string; estimateAt?: string; capacitySource?: string | null;
  inputLimit?: number | null;
  inputCount?: import('./context-requests').InputCount|null;
  compactionTargetTokens?: number | null;
  blockedRequestId?:string|null;
  checkpoint?: { recordId: string; throughSequence: number } | null;
}
export interface SessionCreate { name: string; providerId: string; model: string; effort: string; fastMode?: boolean; requestId: string }
export interface SessionUpdate {
  contextLimit?: ContextLimitPreference;
  selectionRevision?:number;
  revision: number; name?: string; providerId?: string; model?: string; effort?: string; fastMode?: boolean; permissions?: ToolPermissions;
  webSearchEnabled?: boolean;
  environmentNotesEnabled?: boolean;
  imageGenerationEnabled?: boolean;
  roadmapEnabled?: boolean;
  skillOverrides?: Record<string, boolean>;
}
export interface SessionOptions {
  contextLimitDefaults?: ContextLimitDefaults;
  skills?: { id: string; name: string; description: string; available: boolean; reason?: string }[];
  development?: import('./project-development.js').DevelopmentOptions;
  providers: { id: string; name: string; type?: 'openai' | 'api' | 'claude-subscription'; kind?: import('./api-providers.js').ApiProviderKind; unavailableReason?: string; engine?: { toolScope?: 'project' | 'skill'; profile?: string; version?: string; sha256?: string; available: boolean; reason?: string }; models: { id: string; name: string; efforts: string[]; defaultEffort: string; fastModeAvailable: boolean; imageInputs?: 'supported' | 'unsupported' | 'unknown'; inputModalities?: ('text' | 'image' | 'audio')[] | null; available?: boolean; unavailableReasons?: string[]; contextWindow?: number | null; source?: { kind: 'manual' | 'metadata'; recordedAt: string; url?: string } | null }[] }[];
  tools: { id: AgentToolId; defaultEnabled: boolean; defaultReason?:string }[];
  nativeTools?: { id: 'web_search' | 'image_generation'; defaultEnabled: boolean }[];
  engine: { toolScope?: 'project' | 'skill'; profile?: string; version: string; sha256: string; available: boolean; reason?: string };
}
export interface TerminalTimingFields {
  startedAt: string | null; observedAt: string | null; endedAt: string | null;
  elapsedMilliseconds: number | null; deadlineAt: string | null; remainingLifetimeMilliseconds: number | null;
  timing: { version: 1; coverage: string; clock: string | null; limitMilliseconds: number | null; final: boolean | null;
    measurement?: string; bootBound?: boolean; source?: string };
}
export interface SessionItem extends Partial<TerminalTimingFields> {
  apiOrigin?: import('./api-providers.js').ApiResponseOrigin;
  generatedImage?: import('./generated-images.js').GeneratedImage;
  generatedImages?: import('./generated-images.js').GeneratedImage[];
  imageErrors?: string[];
  imageDelivery?: 'pixels' | 'reference-only';
  captureState?: 'confirmed';
  visionAnalysis?: { state: 'not-requested' | 'native' | 'completed' | 'failed' | 'unknown'; text?: string; reason?: string; providerId?: string; model?: string; reportedModel?: string };
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
export interface SessionScreenshot {
  observationMode?: 'vm-diagnostic';
  diagnosticOnly?: true; contentUnconfirmed?: true;
  id:string;projectId:string;sessionId:string;jobId:string;runId:string;toolCallId:string;requestId:string;tool:string;
  publication:number;vmId:string|null;bootId:string|null;createdAt:string|null;
  width:number;height:number;bytes:number;sha256:string;source:'agent-vm-capture';reference:string;
}
export interface ScreenshotPage {
  schema:1;owner:SessionOwner;sessionId:string;available:boolean;reason:string|null;
  items:SessionScreenshot[];nextCursor:string|null;revision:number;watermark:number;
  coverage:{complete:boolean;unqualified:number};
}
export interface SessionDeletionPreview { sessionId: string; name: string; revision: number; scopeHash: string; allowed: boolean; blockers: string[] }
export interface SessionDeletionInput { requestId: string; revision: number; scopeHash: string; confirmName: string }
export interface SessionDeletionReceipt { requestId: string; sessionId: string; state: 'deleting' | 'unknown' | 'deleted'; phase: string; reason?: string; creationRequestIds?: string[] }
export interface AgentEvent { seq: number; kind: string; runId: string | null; payload: unknown; delivery?: 'live'|'replay' }
export interface RemoteReceiptSummary {
  id?: string; requestId?: string; hostId?: string; hostName?: string; operation?: string;
  state?: string; phase?: string; deadlineAt?: string; code?: number; stopRequested?: boolean;
  binding?: { id: string; endpointRevision: number; credentialRevision: number; trustRevision: number };
  localClientEndConfirmed?: boolean; remoteProcessEndConfirmed?: boolean; commandReturnConfirmed?: boolean; commandExitCode?: number | null;
}

export interface NativeImageCapability { schema: 1; providerId?: string; model?: string; engine?: AgentSession['engine']; checkedAt?: string; state: 'available' | 'unavailable' | 'unknown'; available: boolean; qualified: boolean; reason: string; accountType?: string; accountPlan?: string; accountSha256?: string; inputModalities?: ('text' | 'image' | 'audio')[] | null; policySha256?: string }
