/** Additive API connections; existing OpenAI subscription Provider is unchanged. */
export type ApiProviderKind = 'openrouter' | 'openai-compatible' | 'local';
export type ApiProtocol = 'responses' | 'chat-completions';
export type ApiAuth = 'none' | 'bearer';
export interface OpenRouterSettings {
  order: string[]; only: string[]; allowFallbacks: boolean;
  attribution: { url: string; title: string } | null;
}
export interface ApiProvider {
  id: string; type: 'api'; kind: ApiProviderKind; name: string;
  baseUrl: string; protocol: ApiProtocol; auth: ApiAuth;
  revision: number; credentialRevision: number; keyConfigured: boolean;
  enabled: boolean; status: 'configured' | 'disconnected';
  createdAt: string; updatedAt: string;
  /** Configuration alone never establishes model/tool/Goal compatibility. */
  runtime: 'not-qualified';
  openrouter?: OpenRouterSettings;
}
export interface ApiProviderCreate {
  requestId: string; name: string; kind: ApiProviderKind; baseUrl: string;
  protocol: ApiProtocol; auth: ApiAuth; key?: string; openrouter?: OpenRouterSettings;
}
export interface ApiProviderUpdate {
  requestId: string; revision: number; name?: string; baseUrl?: string;
  protocol?: ApiProtocol; auth?: ApiAuth; key?: string | null; enabled?: boolean; openrouter?: OpenRouterSettings;
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
export type ApiCapability = 'supported' | 'unsupported' | 'unknown';
export type ApiEffort = 'none' | 'minimal' | 'low' | 'medium' | 'high' | 'xhigh';
export interface ApiModelFacts {
  id: string; name: string; contextWindow: number | null;
  maxOutputTokens: number | null;
  capabilities: Record<'text' | 'functionTools' | 'streaming' | 'imageInput' | 'reasoning' | 'webSearch' | 'imageGeneration' | 'goals', ApiCapability>;
  efforts: ApiEffort[]; defaultEffort: ApiEffort | null;
}
export interface ApiModel extends ApiModelFacts {
  declaredCapabilities: ApiModelFacts['capabilities'];
  available: boolean; unavailableReasons: string[];
  source: { kind: 'metadata' | 'manual'; recordedAt: string; url?: string } | null;
}
export interface ApiModelCatalog {
  providerId: string; revision: number; configRevision: number; stale: boolean;
  checkedAt: string | null; metadataCurrent: boolean; checkedCredentialRevision: number | null;
  truncated: boolean; models: ApiModel[];
}
export interface ApiModelMutation {
  requestId: string; providerId: string; state: 'pending' | 'complete' | 'failed' | 'unknown';
  catalogRevision?: number; modelId?: string; error?: string;
}
/** Run-bound observations; requested model and local IDs are not provider receipts. */
export interface ApiResponseOrigin {
  providerId: string; configRevision: number; ordinal: number; requestedModel: string;
  reportedRequested: string | null; reportedModel: string | null; reportedBackend: string | null;
  endpointModel: string | null; endpointBackend: string | null; strategy: string | null;
  gatewayAttempt: number | null; providerResponseId: string | null; localResponseId: string;
  finishReason: string | null;
  usage: { input_tokens: number; output_tokens: number; total_tokens: number;
    input_tokens_details?: { cached_tokens?: number }; output_tokens_details?: { reasoning_tokens?: number } } | null;
}
