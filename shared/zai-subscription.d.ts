export interface ZaiQuotaWindow {
  id: string; type: string; unit: 'credits' | 'tokens' | 'requests' | 'unknown'; window: string;
  nativeUnit: number | string | null; nativeCount: number | null;
  maximum: number | null; used: number | null; remaining: number | null; percentage: number | null; resetAt: string | null;
}
export interface ZaiSubscriptionLimits {
  providerId: string; configRevision: number; credentialRevision: number;
  state: 'current' | 'stale' | 'unknown'; scopeId: string | null; checkedAt: string | null;
  error: string | null; level: string | null; limits: ZaiQuotaWindow[];
  monitor?: { lastAttemptAt: string | null; nextAutoAt: string | null; failures: number; retryAfterAt: string | null; lastRequestId: string | null; pendingRequestId: string | null; pendingState: 'pending' | 'unknown' | null };
  holds?: { model: string | null; reason: string; resetAt: string | null; observedAt: string }[];
}
export interface ZaiQuotaMutation {
  requestId: string; providerId: string; state: 'pending' | 'complete' | 'failed' | 'unknown'; error?: string;
}
