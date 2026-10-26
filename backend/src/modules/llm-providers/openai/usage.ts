import type { CreditBalance, ProviderUsage, ResetCredit, ResetOutcome, ResetRequest, UsageLimit, UsageWindow } from '../../../../../shared/llm-providers.js';
import type { AuthClient } from './codex-client.js';

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function text(value: unknown, maxLength = 512): string | null {
  return typeof value === 'string' && value.length > 0 ? value.slice(0, maxLength) : null;
}

function nonnegative(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
}

function timestamp(value: unknown): string | null {
  const seconds = nonnegative(value);
  return seconds !== null && seconds * 1000 <= 8.64e15 ? new Date(seconds * 1000).toISOString() : null;
}

function window(value: unknown): UsageWindow | null {
  const raw = object(value);
  if (!raw) return null;
  const usedPercent = nonnegative(raw.usedPercent);
  return { usedPercent, remainingPercent: usedPercent === null ? null : Math.max(0, 100 - usedPercent),
    windowDurationMins: nonnegative(raw.windowDurationMins), resetsAt: timestamp(raw.resetsAt) };
}

function credit(value: unknown): ResetCredit | null {
  const raw = object(value);
  const id = text(raw?.id);
  if (!raw || !id) return null;
  const status = raw.status === 'available' || raw.status === 'redeeming' || raw.status === 'redeemed' ? raw.status : 'unknown';
  return { id, type: raw.resetType === 'codexRateLimits' ? 'codexRateLimits' : 'unknown', status,
    title: text(raw.title), description: text(raw.description, 2048), grantedAt: timestamp(raw.grantedAt), expiresAt: timestamp(raw.expiresAt) };
}

function creditBalance(value: unknown): CreditBalance | null {
  const raw = object(value);
  if (!raw) return null;
  const balance = typeof raw.balance === 'string' ? raw.balance.trim() : null;
  return { hasCredits: typeof raw.hasCredits === 'boolean' ? raw.hasCredits : null,
    unlimited: typeof raw.unlimited === 'boolean' ? raw.unlimited : null,
    balance: balance && balance.length <= 256 && /^-?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(balance) ? balance : null };
}

/** Explicit public DTO: never forward account IDs, auth fields or arbitrary backend banners. */
export function normalizeUsage(value: unknown): ProviderUsage {
  const raw = object(value);
  if (!raw) throw new Error('Invalid usage response.');
  const buckets = Object.entries(object(raw.rateLimitsByLimitId) ?? {}).filter(([, bucket]) => object(bucket));
  if (!buckets.length && object(raw.rateLimits)) buckets.push(['codex', raw.rateLimits]);
  if (!buckets.length) throw new Error('No usage limits returned.');
  const limits: UsageLimit[] = buckets.slice(0, 100).map(([key, value]) => {
    const bucket = object(value)!;
    const id = text(bucket.limitId) ?? key.slice(0, 512);
    return { id, credits: creditBalance(bucket.credits), name: text(bucket.limitName) ?? (id === 'codex' ? 'Codex' : id),
      primary: window(bucket.primary), secondary: window(bucket.secondary), limitReached: !!text(bucket.rateLimitReachedType) };
  });
  const resets = object(raw.rateLimitResetCredits);
  const count = nonnegative(resets?.availableCount);
  return { fetchedAt: new Date().toISOString(),
    ordinaryUsageAllowed: typeof raw.ordinaryUsageAllowed === 'boolean' ? raw.ordinaryUsageAllowed : null,
    limits, resetCredits: resets ? { availableCount: count !== null && Number.isSafeInteger(count) ? count : null,
      credits: Array.isArray(resets.credits) ? resets.credits.slice(0, 100).map(credit).filter((item): item is ResetCredit => item !== null) : null } : null };
}

export async function readUsage(client: AuthClient): Promise<ProviderUsage> {
  // Details are included by default. Do not opt into reserve experiments or redemption.
  return normalizeUsage(await client.request('account/rateLimits/read'));
}

export async function redeemReset(client: AuthClient, request: ResetRequest): Promise<ResetOutcome> {
  const result = object(await client.request('account/rateLimitResetCredit/consume', {
    idempotencyKey: request.idempotencyKey, ...(request.creditId ? { creditId: request.creditId } : {}),
  }));
  const outcome = result?.outcome;
  if (outcome !== 'reset' && outcome !== 'alreadyRedeemed' && outcome !== 'nothingToReset' && outcome !== 'noCredit') {
    throw new Error('Unknown reset result.');
  }
  return outcome;
}
