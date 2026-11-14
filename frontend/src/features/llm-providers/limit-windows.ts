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
  durationMinutes: number | null;
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

export function usageWindows(sample: UsageObservation | null, model?: string): LimitWindow[] {
  return sample?.usage?.limits.filter(limit => !model || limit.id === 'codex' || limit.id === model)
    .flatMap(limit => ([['primary', limit.primary], ['secondary', limit.secondary]] as const)
    .flatMap(([key, window]) => window ? [{ id: limit.id + ':' + key, label: duration(window.windowDurationMins, key === 'primary' ? 'Primary window' : 'Secondary window'),
      scope: limit.name, remainingPercent: sample.state === 'unknown' ? null : validPercent(window.remainingPercent), resetsAt: reset(window.resetsAt),
      durationMinutes: window.windowDurationMins && window.windowDurationMins > 0 ? window.windowDurationMins : null }] : [])) ?? [];
}

const budgetNames: Record<string, string> = { key_limit: 'API key', member: 'Member', user: 'User', organization: 'Organization', workspace: 'Workspace', guardrail: 'Guardrail' };
function budgetWindows(sample: ConnectionLimits, onlyFinite: boolean): LimitWindow[] {
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
  return budgets.filter(budget=>!onlyFinite || budget.limitUsd!==null && !budget.unlimited).map((budget, index) => {
    const maximum = budget.limitUsd, left = budget.remainingUsd;
    const valid = maximum !== null && left !== null && Number.isFinite(maximum) && Number.isFinite(left) && maximum >= 0 && left >= 0 && left <= maximum;
    const remaining = valid ? maximum === 0 ? 0 : left / maximum * 100 : null;
    return { id: budget.scope + ':' + (budget.resetInterval ?? 'cap') + ':' + index,
      label: budget.resetInterval ? budget.resetInterval.charAt(0).toUpperCase() + budget.resetInterval.slice(1) : 'Spending cap',
      scope: (budgetNames[budget.scope] ?? budget.scope) + ' budget · USD',
      remainingPercent: sample.state === 'unknown' || budget.unlimited ? null : validPercent(remaining),
      unlimited: sample.state !== 'unknown' && budget.unlimited, resetsAt: reset(budget.resetsAt),
      durationMinutes: budget.resetInterval ? {daily:1440,weekly:10080,monthly:43200}[budget.resetInterval] : null };
  });
}

type ClaudeWindows = NonNullable<ConnectionLimits['claude']>['windows'];
type Model = {id: string; name?: string};

export function claudeWindows(windows: ClaudeWindows, state: ConnectionLimits['state'], model?: Model): LimitWindow[] {
  const labels = [model?.id.toLowerCase(), model?.name?.toLowerCase()];
  return windows.filter(w => {
    if (model && w.scope !== 'account') {
      if ((w.scope === 'opus' || w.scope === 'sonnet') && !labels.some(label => label?.includes(w.scope))) return false;
      if (w.scope === 'native-model-label' && !labels.includes(w.label.toLowerCase())) return false;
      if (w.scope === 'oauth-apps') return false;
      if (w.scope === 'native-meter' && !['session','weekly_all'].includes(w.kind ?? '')
          && !labels.includes(w.label.toLowerCase())) return false;
    }
    // Only known account-meter aliases with identical observations collapse.
    const canonical = w.scope === 'native-meter' ? w.kind === 'session' ? 'five_hour' : w.kind === 'weekly_all' ? 'seven_day' : null : null;
    return !canonical || !windows.some(other => other.id === canonical && other.scope === 'account'
      && other.remainingPercent === w.remainingPercent && other.usedPercent === w.usedPercent && other.resetsAt === w.resetsAt);
  }).map(w => ({ id: w.id, label: w.label, scope: w.scope,
    remainingPercent: state === 'unknown' ? null : validPercent(w.remainingPercent), resetsAt: reset(w.resetsAt),
    durationMinutes: w.id === 'five_hour' || w.kind === 'session' ? 300
      : w.id.startsWith('seven_day') || w.kind?.startsWith('weekly') ? 10080 : null }));
}

export function connectionWindows(sample: ConnectionLimits | null, model?: Model): LimitWindow[] {
  if (!sample) return [];
  if (sample.zai) return sample.zai.limits.filter(w => ['CREDIT_LIMIT', 'TOKENS_LIMIT'].includes(w.type) && ['5-hour', 'Weekly'].includes(w.window))
    .map(w => ({ id: w.id, label: w.window, scope: w.unit,
      remainingPercent: sample.state === 'unknown' ? null : zaiRemainingUsage({ ...sample.zai!, state: sample.state, limits: [w] }),
      resetsAt: reset(w.resetAt), durationMinutes: w.window === '5-hour' ? 300 : 10080 }));
  if (sample.claude) return claudeWindows(sample.claude.windows, sample.state, model);
  if (!sample.openrouter) return [];
  const windows = budgetWindows(sample, !!model);
  const daily = sample.openrouter.freeModelDailyRequests;
  if (model?.id.endsWith(':free') && daily?.limit != null) {
    const remaining = daily.remaining ?? (daily.used != null ? Math.max(0,daily.limit-daily.used) : null);
    windows.push({id:'free-requests',label:'Daily requests',scope:'Free model requests',
      durationMinutes:1440,resetsAt:null,remainingPercent:sample.state==='unknown' || remaining==null
        ? null : validPercent(daily.limit > 0 ? remaining/daily.limit*100 : 0)});
  }
  return windows;
}
