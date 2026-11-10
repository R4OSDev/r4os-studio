/** Original provider request inspection, scoped to one project/skill session. */
export interface InputCount {
  schema?:1; tokens:number|null; bytes:number; characters?:number; textCharacters?:number;
  source?:'local-tokenizer'|'character-estimate'|'unavailable'; method:string; methodVersion?:string;
  accuracy?:'estimated'|'unavailable'; fallbackReason?:string|null; requestSha256?:string;
  tokenizer?:{library:string;version:string;encoding:string;manifestSha256:string}|null;
  reserves?:{framing:number;media:number}; admissionTokens?:number;
  mediaCost?:{version:1;qualifiedImages:number;conservativeImages:number;profile:string|null};
  providerCount?:{id:string;purpose:'input-count';state:'checking'|'complete'|'unavailable'|'interrupted';
    inputTokens:number|null;createdAt:string;finishedAt?:string;error?:{code:string|number;httpStatus:number|null}};
}
export interface RequestContext {
  schema: 1; state: 'estimated' | 'unavailable'; method: string | null;
  estimatedInput: number | null; modelWindow: number | null; inputLimit: number | null;
  capacity: number | null; capacityBasis: 'effective-input-limit' | 'model-window';
  outputReserve: number | null; policyEnforced: boolean; free: number | null; overflow: number | null;
  reason: string | null; categories: {id:'system'|'tools'|'conversation'|'other';label:string;tokens:number;bytes:number;characters?:number}[];
  counting?:InputCount;
}
export interface ContextRequest {
  id: string; sequence: number; runId: string; model: string; providerId: string; protocol: string;
  purpose: string; at: string; capturedAt: string; responseAt: string | null; httpStatus: number | null;
  bytes: number; sha256: string; bodyAvailable: boolean; phase: string;
  status: 'dispatch-attempted' | 'response-received' | 'blocked-before-send'; blockedReason?:string|null;
}
export interface ContextRequestDetail extends ContextRequest {
  context: RequestContext | null; older: string | null; newer: string | null;
  position: number; total: number; policy: Record<string,unknown> | null;
  usage: {input:number|null;cachedInput:number|null;cacheWrite:number|null;output?:number|null;source:string};
  summaryBudget?:{version:1;targetTokens:number;maxOutputTokens:number|null;timeoutSeconds:number;effort:string};
}
export interface ContextRequestPage {
  requests: ContextRequest[]; nextBefore: number | null; notice: string;
  kind?:'dispatched'|'blocked'; blockedAvailable?:boolean;
  retention: {maxRequests:number;compressedBodyBytes:number;droppedRequests:number};
}
export interface ContextRequestChunk {
  requestId: string; offset: number; nextOffset: number | null; bytes: number; base64: string;
}
