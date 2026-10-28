import type { SessionOwner } from './agent-sessions.js';

/** Native Codex status, distinct from Studio's last confirmed button intent. */
export type NativeGoalStatus = 'active' | 'paused' | 'blocked' | 'usageLimited' | 'budgetLimited' | 'complete';
export interface NativeGoal {
  threadId: string; objective: string; status: NativeGoalStatus;
  tokensUsed: number; timeUsedSeconds: number; createdAt: number; updatedAt: number;
  tokenBudget?: number | null;
}
export type GoalAction = 'save' | 'play' | 'pause' | 'stop';
export interface GoalCommand {
  requestId: string; revision: number; action: GoalAction; objective?: string; sessionRevision?: number;
}
export interface SessionGoal {
  owner: SessionOwner; sessionId: string; threadId: string | null;
  revision: number; goal: NativeGoal | null;
  lastIntent: GoalAction | null;
  phase: 'idle' | 'pending' | 'pausing' | 'unknown';
  requestId?: string; runId?: string; reason?: string;
}
export interface GoalReceipt {
  requestId: string; action: GoalAction; state: 'pending' | 'confirmed' | 'failed' | 'unknown';
  snapshot: SessionGoal; reason?: string;
}
export type AttachmentInputMode = 'localImage' | 'text' | 'pdfText';
/** Private paths and file bytes never appear in public event/HTTP metadata. */
export interface SessionAttachment {
  id: string; sessionId: string; name: string; mediaType: string;
  size: number; sha256: string; mode: AttachmentInputMode;
  state: 'ready' | 'rejected'; createdAt: string;
  width?: number; height?: number; pages?: number;
  extractedBytes?: number; limitation?: string;
}
export interface RunAttachment {
  id: string; sha256: string; mediaType: string; size: number; mode: AttachmentInputMode;
}
export interface AgentInputCapabilities {
  goal: { available: boolean; reason?: string; maxObjectiveChars: number; budgetControls: false };
  attachments: { available: boolean; reason?: string; maxFiles: number; maxFileBytes: number; maxRunBytes: number };
}
