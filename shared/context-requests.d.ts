/** Original provider request inspection, scoped to one project/skill session. */
export interface RequestContext {
  schema: 1; state: 'estimated' | 'unavailable'; method: string | null;
  estimatedInput: number | null; modelWindow: number | null; inputLimit: number | null;
  capacity: number | null; capacityBasis: 'effective-input-limit' | 'model-window';
  outputReserve: number | null; policyEnforced: boolean; free: number | null; overflow: number | null;
  reason: string | null; categories: {id:'system'|'tools'|'conversation'|'other';label:string;tokens:number;bytes:number}[];
}
export interface ContextRequest {
  id: string; sequence: number; runId: string; model: string; providerId: string; protocol: string;
  purpose: string; at: string; capturedAt: string; responseAt: string | null; httpStatus: number | null;
  bytes: number; sha256: string; bodyAvailable: boolean; phase: string;
  status: 'dispatch-attempted' | 'response-received';
}
export interface ContextRequestDetail extends ContextRequest {
  context: RequestContext | null; older: string | null; newer: string | null;
  position: number; total: number; policy: Record<string,unknown> | null;
  usage: {input:number|null;cachedInput:number|null;cacheWrite:number|null;source:string};
}
export interface ContextRequestPage {
  requests: ContextRequest[]; nextBefore: number | null; notice: string;
  retention: {maxRequests:number;compressedBodyBytes:number;droppedRequests:number};
}
export interface ContextRequestChunk {
  requestId: string; offset: number; nextOffset: number | null; bytes: number; base64: string;
}
