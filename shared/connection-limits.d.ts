import type { ClaudeSubscriptionLimits } from './claude-subscription';
import type { ZaiSubscriptionLimits } from './zai-subscription';

export interface OpenRouterBudget {
  scope: string; limitUsd: number | null; spendUsd: number | null; remainingUsd: number | null;
  unlimited: boolean; resetInterval: 'daily' | 'weekly' | 'monthly' | null;
  resetsAt: string | null; includeByok: boolean | null;
}
export interface OpenRouterKeyLimits {
  currency: 'USD'; keyBudget: OpenRouterBudget; effectiveBudget: OpenRouterBudget | null;
  selectedBudget: OpenRouterBudget | null; budgets: OpenRouterBudget[];
  usage: { daily: number | null; weekly: number | null; monthly: number | null };
  freeModelDailyRequests: { used: number | null; limit: number | null; remaining: number | null } | null;
  source: string;
}

/** One account observation shared by a connection's detail and navigation views. */
export interface ConnectionLimits {
  providerId: string; configRevision: number; credentialRevision: number;
  state: 'current' | 'stale' | 'unknown'; checkedAt: string | null; error: string | null;
  remainingPercent: number | null;
  claude?: ClaudeSubscriptionLimits;
  openrouter?: OpenRouterKeyLimits;
  zai?: ZaiSubscriptionLimits;
}
