import type { ProviderUsage } from '../../../../shared/llm-providers.js';
import type { ZaiSubscriptionLimits } from '../../../../shared/zai-subscription';

/** Model allowance only; unrelated MCP request windows never set this value. */
export function zaiRemainingUsage(sample: ZaiSubscriptionLimits | null): number | null {
  if (!sample || !sample.scopeId || sample.state === 'unknown' || !Array.isArray(sample.limits)) return null;
  const windows = sample.limits.filter(w => ['CREDIT_LIMIT', 'TOKENS_LIMIT'].includes(w.type) && ['5-hour', 'Weekly'].includes(w.window));
  const values: number[] = [];
  const valid = (value: number | null): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0;
  for (const window of windows) {
    if (window.unit !== (window.type === 'CREDIT_LIMIT' ? 'credits' : 'tokens')) return null;
    let remaining: number;
    if (valid(window.maximum) && window.maximum > 0 && valid(window.remaining)) {
      if (window.remaining > window.maximum) return null;
      if (valid(window.used) && Math.abs(Math.max(0, window.maximum - window.used) - window.remaining) > Math.max(1, window.maximum) * 1e-9) return null;
      remaining = window.remaining / window.maximum * 100;
      // Monitoring may report whole used percentages alongside exact counters.
      if (valid(window.percentage) && (window.percentage > 100 || Math.abs(100 - remaining - window.percentage) > 1)) return null;
    } else if (valid(window.percentage) && window.percentage <= 100) remaining = 100 - window.percentage;
    else return null;
    values.push(remaining);
  }
  return values.length ? Math.min(...values) : null;
}

export function remainingUsage(usage: ProviderUsage | null): number | null {
  if (!usage || !Array.isArray(usage.limits)) return null;
  const values = usage.limits.flatMap((limit) => [limit.primary?.remainingPercent, limit.secondary?.remainingPercent])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100);
  return values.length ? Math.min(...values) : null;
}

export function percent(value: number | null): string {
  return value === null ? 'Not reported' : `${new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(value)}%`;
}

export function dateTime(value: string | null): string {
  return value === null ? 'Not reported' : new Intl.DateTimeFormat('en', {
    dateStyle: 'medium', timeStyle: 'long',
  }).format(new Date(value));
}

export function duration(minutes: number | null, fallback: string): string {
  if (minutes === null || minutes <= 0) return fallback;
  for (const [unit, size] of [['week', 10080], ['day', 1440], ['hour', 60], ['minute', 1]] as const) {
    if (minutes % size === 0) {
      const count = minutes / size;
      return `${count} ${unit}${count === 1 ? '' : 's'}`;
    }
  }
  return fallback;
}

export function untilReset(value: string | null, now: number): string {
  if (value === null) return 'Reset time not reported';
  const minutes = Math.ceil((Date.parse(value) - now) / 60_000);
  if (minutes <= 0) return 'Reset time passed — refresh usage for the current limit';
  if (minutes < 60) return `Resets in ${minutes}m`;
  if (minutes < 1440) return `Resets in ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `Resets in ${Math.floor(minutes / 1440)}d ${Math.floor((minutes % 1440) / 60)}h`;
}
