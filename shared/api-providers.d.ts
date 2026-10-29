/** Additive API connections; existing OpenAI subscription Provider is unchanged. */
export type ApiProviderKind = 'openrouter' | 'openai-compatible' | 'local';
export type ApiProtocol = 'responses' | 'chat-completions';
export type ApiAuth = 'none' | 'bearer';
export interface ApiProvider {
  id: string; type: 'api'; kind: ApiProviderKind; name: string;
  baseUrl: string; protocol: ApiProtocol; auth: ApiAuth;
  revision: number; credentialRevision: number; keyConfigured: boolean;
  enabled: boolean; status: 'configured' | 'disconnected';
  createdAt: string; updatedAt: string;
  /** Configuration alone never establishes model/tool/Goal compatibility. */
  runtime: 'not-qualified';
}
export interface ApiProviderCreate {
  requestId: string; name: string; kind: ApiProviderKind; baseUrl: string;
  protocol: ApiProtocol; auth: ApiAuth; key?: string;
}
export interface ApiProviderUpdate {
  requestId: string; revision: number; name?: string; baseUrl?: string;
  protocol?: ApiProtocol; auth?: ApiAuth; key?: string | null; enabled?: boolean;
}
export interface ApiProviderMutation {
  requestId: string; state: 'pending' | 'complete'; provider: ApiProvider;
}
/** Run snapshots contain these public references, never the secret value. */
export interface ApiProviderBinding {
  providerId: string; configRevision: number; credentialRevision: number;
  baseUrl: string; protocol: ApiProtocol; auth: ApiAuth;
}

/** Missing provider metadata stays unknown until a specific model is qualified. */
export interface ApiModel {
  id: string; name: string; contextWindow: number | null;
  capabilities: {
    text: 'supported' | 'unsupported' | 'unknown';
    functionTools: 'supported' | 'unsupported' | 'unknown';
    imageInput: 'supported' | 'unsupported' | 'unknown';
    reasoning: 'supported' | 'unsupported' | 'unknown';
    webSearch: 'supported' | 'unsupported' | 'unknown';
    imageGeneration: 'supported' | 'unsupported' | 'unknown';
    goals: 'supported' | 'unsupported' | 'unknown';
  };
}
