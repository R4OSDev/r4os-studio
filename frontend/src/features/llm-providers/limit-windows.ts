import type { ProviderUsage } from '../../../../shared/llm-providers';
import type { ConnectionLimits, OpenRouterBudget } from '../../../../shared/connection-limits';
import type { ZaiSubscriptionLimits } from '../../../../shared/zai-subscription';
import { duration, zaiRemainingUsage } from './usage-format';

export interface UsageObservation {
  usage: ProviderUsage | null;
  state: 'current' | 'stale' | 'unknown';
  error: string | null;
}
export interface LimitWindow {
  id: string; label: string; scope: string;
  remainingPercent: number | null; resetsAt: string | null; unlimited?: boolean;
}

const validPercent = (value: number | null) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
const reset = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? value : null;

export function usageIsStale(usage: ProviderUsage | null, now: number): boolean {
  return !!usage && (!Number.isFinite(Date.parse(usage.fetchedAt)) || now - Date.parse(usage.fetchedAt) > 120_000);
}

export function zaiSnapshot(value: ZaiSubscriptionLimits): ConnectionLimits {
  return { providerId: value.providerId, configRevision: value.configRevision, credentialRevision: value.credentialRevision,
    state: value.state, checkedAt: value.checkedAt, error: value.error, remainingPercent: zaiRemainingUsage(value), zai: value };
}

export function usageWindows(sample: UsageObservation | null): LimitWindow[] {
  return sample?.usage?.limits.flatMap(limit => ([['primary', limit.primary], ['secondary', limit.secondary]] as const)
    .flatMap(([key, window]) => window ? [{ id: limit.id + ':' + key, label: duration(window.windowDurationMins, key === 'primary' ? 'Primary window' : 'Secondary window'),
      scope: limit.name, remainingPercent: sample.state === 'unknown' ? null : validPercent(window.remainingPercent), resetsAt: reset(window.resetsAt) }] : [])) ?? [];
}

const budgetNames: Record<string, string> = { key_limit: 'API key', member: 'Member', user: 'User', organization: 'Organization', workspace: 'Workspace', guardrail: 'Guardrail' };
function budgetWindows(sample: ConnectionLimits): LimitWindow[] {
  const quota = sample.openrouter!;
  const budgets: OpenRouterBudget[] = [];
  for (const row of [quota.selectedBudget, quota.effectiveBudget, ...quota.budgets, quota.keyBudget]) {
    if (!row) continue;
    // The key/effective/list representations can describe the very same cap;
    // a missing timestamp does not turn it into a second allowance.
    const same = budgets.find(b => b.scope === row.scope && b.resetInterval === row.resetInterval && b.limitUsd === row.limitUsd
      && b.remainingUsd === row.remainingUsd && b.spendUsd === row.spendUsd && b.unlimited === row.unlimited
      && b.includeByok === row.includeByok && (!b.resetsAt || !row.resetsAt || b.resetsAt === row.resetsAt));
    if (same) { if (!same.resetsAt && row.resetsAt) same.resetsAt = row.resetsAt; }
    else budgets.push({ ...row });
  }
  return budgets.map((budget, index) => {
    const maximum = budget.limitUsd, left = budget.remainingUsd;
    const valid = maximum !== null && left !== null && Number.isFinite(maximum) && Number.isFinite(left) && maximum >= 0 && left >= 0 && left <= maximum;
    const remaining = valid ? maximum === 0 ? 0 : left / maximum * 100 : null;
    return { id: budget.scope + ':' + (budget.resetInterval ?? 'cap') + ':' + index,
      label: budget.resetInterval ? budget.resetInterval.charAt(0).toUpperCase() + budget.resetInterval.slice(1) : 'Spending cap',
      scope: (budgetNames[budget.scope] ?? budget.scope) + ' budget · USD',
      remainingPercent: sample.state === 'unknown' || budget.unlimited ? null : validPercent(remaining),
      unlimited: sample.state !== 'unknown' && budget.unlimited, resetsAt: reset(budget.resetsAt) };
  });
}

export function connectionWindows(sample: ConnectionLimits | null): LimitWindow[] {
  if (!sample) return [];
  if (sample.zai) return sample.zai.limits.filter(w => ['CREDIT_LIMIT', 'TOKENS_LIMIT'].includes(w.type) && ['5-hour', 'Weekly'].includes(w.window))
    .map(w => ({ id: w.id, label: w.window, scope: w.unit,
      remainingPercent: sample.state === 'unknown' ? null : zaiRemainingUsage({ ...sample.zai!, state: sample.state, limits: [w] }), resetsAt: reset(w.resetAt) }));
  if (sample.claude) {
    const windows = sample.claude.windows;
    return windows.filter(w => {
      // Only known account-meter aliases with identical observations collapse;
      // model scopes and genuinely different reported limits remain separate.
      const canonical = w.scope === 'native-meter' ? w.kind === 'session' ? 'five_hour' : w.kind === 'weekly_all' ? 'seven_day' : null : null;
      return !canonical || !windows.some(other => other.id === canonical && other.scope === 'account'
        && other.remainingPercent === w.remainingPercent && other.usedPercent === w.usedPercent && other.resetsAt === w.resetsAt);
    }).map(w => ({ id: w.id, label: w.label, scope: w.scope,
      remainingPercent: sample.state === 'unknown' ? null : validPercent(w.remainingPercent), resetsAt: reset(w.resetsAt) }));
  }
  return sample.openrouter ? budgetWindows(sample) : [];
}
