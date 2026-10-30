/** Native Claude-plan identity; never an Anthropic API key or Codex endpoint. */
export interface ClaudeSubscriptionProvider {
  id: string; type: 'claude-subscription'; name: string;
  revision: number; profileRevision: 1; runtimeProfileId: string;
  status: 'not-connected'; enabled: false;
  auth: { kind: 'native-plan'; state: 'not-connected' };
  createdAt: string; updatedAt: string;
  /** Authentication and limit enforcement are qualified in later stages. */
  account: null;
}
export interface ClaudeProviderCreate { requestId: string; name: string }
export interface ClaudeProviderMutation {
  requestId: string; state: 'complete'; provider: ClaudeSubscriptionProvider;
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
