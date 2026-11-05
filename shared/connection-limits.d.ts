import type { ClaudeSubscriptionLimits } from './claude-subscription';

/** One account observation shared by a connection's detail and navigation views. */
export interface ConnectionLimits {
  providerId: string; configRevision: number; credentialRevision: number;
  state: 'current' | 'stale' | 'unknown'; checkedAt: string | null; error: string | null;
  remainingPercent: number | null;
  claude?: ClaudeSubscriptionLimits;
}
