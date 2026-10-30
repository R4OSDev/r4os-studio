/** Native Claude-plan identity; never an Anthropic API key or Codex endpoint. */
export interface ClaudeSubscriptionProvider {
  id: string; type: 'claude-subscription'; name: string;
  revision: number; profileRevision: 1; runtimeProfileId: string;
  status: 'not-connected' | 'connected' | 'reauthentication-required' | 'unsupported'; enabled: false;
  auth: { kind: 'native-plan'; state: ClaudeSubscriptionProvider['status'] };
  createdAt: string; updatedAt: string;
  /** Native auth evidence; model and overage qualification remain separate. */
  account: null | { email: string | null; orgId: string | null; orgName: string | null;
    plan: 'pro' | 'max'; authMethod: 'claude.ai'; apiProvider: 'firstParty'; checkedAt: string };
}
export interface ClaudeProviderCreate { requestId: string; name: string }
export interface ClaudeProviderMutation {
  requestId: string; state: 'complete'; provider: ClaudeSubscriptionProvider;
}
export type ClaudeAuthAction = 'connect' | 'status' | 'disconnect' | 'limits' | 'catalog';
export interface ClaudeAuthRequest { requestId: string; revision: number; action: ClaudeAuthAction }
export interface ClaudeAuthOperation {
  requestId: string; providerId: string; action: ClaudeAuthAction; revision: number;
  state: 'pending' | 'waiting' | 'complete' | 'failed' | 'cancelled' | 'expired' | 'unconfirmed' | 'reconciled';
  message: string | null; createdAt: string; updatedAt: string; provider: ClaudeSubscriptionProvider;
  /** Present only in the initiating live browser session, never persisted. */
  authorizationUrl?: string; expiresInSeconds?: number;
  limits?: ClaudeSubscriptionLimits;
  catalog?: ClaudeModelCatalog | null;
}
export interface ClaudeModelCatalog {
  schema: 1; source: string; receivedAt: string; providerId: string; providerRevision: number;
  accountIdentity: string | null; runtimeProfileId: string; sessionProfileId?: string; requestId: string; sessionModelsQualified: boolean;
  models: { id: string; nativeValue: string; resolvedModel: string | null; name: string; description: string;
    aliases: string[]; efforts: string[]; defaultEffort: string; supportsEffort: boolean | null;
    adaptiveThinking: boolean | null; fastModeAdvertised: boolean | null; fastModeAvailable: false;
    contextWindow: null; imageInputs: 'unknown'; inputModalities: ['text']; available: boolean;
    unavailableReasons: string[]; source: 'native-supportedModels'; entitlement: 'not-verified-by-model-advertisement' }[];
}
export interface ClaudeSubscriptionLimits {
  schema: 1; source: string; receivedAt: string; providerId: string; providerRevision: number;
  accountIdentity: string | null; requestId: string; plan: 'pro' | 'max' | null;
  coverage: 'available' | 'partial' | 'unavailable'; extraUsageEnabled: boolean | null; message: string;
  windows: { id: string; label: string; scope: string; usedPercent: number | null; remainingPercent: number | null; resetsAt: string | null }[];
}
export interface ClaudeRateObservation {
  studioSessionId: string; providerId: string; runId: string; accountIdentity: string | null;
  schema: 1; source: string; receivedAt: string; status: 'allowed' | 'allowed_warning' | 'rejected' | 'unavailable';
  scope: string | null; usedPercent: number | null; resetsAt: string | null;
  overageEnabled: boolean | null; usingOverage: boolean;
}
export interface ClaudeQuotaHold {
  id: string; createdAt: string; reasonCode: 'subscription_limit' | 'overage_unconfirmed'; reason: string;
  providerId: string; sourceRequestId: string | null;
}
export interface ClaudeRuntimeStatus {
  id: string; version: string; sdkVersion: string; sha256: string; sdkArchiveSha256: string;
  qualified: Record<string, boolean>;
}
export interface ClaudeEngineBinding {
  kind: 'claude-code'; profile: 'studio-claude-sdk-v1'; profileRevision: 1;
  providerId: string; studioSessionId: string; nativeSessionId: string | null;
  runtimeProfileId: string; version: string; sha256: string;
  sdkVersion: string; sdkArchiveSha256: string;
}
export interface ClaudeCapabilities {
  metadataControl: boolean; authenticatedSubscription: boolean;
  modelTurns: boolean; studioTools: boolean; goals: boolean; overageProtection: boolean;
}
export interface ClaudeMessageIdentity {
  studioRequestId: string; nativeSessionId: string | null;
  nativeMessageId: string | null; providerMessageId: string | null;
  /** Kept unknown unless the native protocol actually reports one. */
  nativeTurnId: string | null; nativeToolUseId: string | null;
}
