import type { ConnectionLimits, OpenRouterBudget } from '../../../../../shared/connection-limits';

const money = (value: number | null) => value === null ? 'Unknown' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(value);
const names: Record<string, string> = { key_limit: 'API key', member: 'Member', user: 'User', organization: 'Organization', workspace: 'Workspace', guardrail: 'Guardrail' };
const label = (scope: string) => names[scope] ?? scope;
export function OpenRouterLimitsView({ sample }: { sample: ConnectionLimits | null }) {
  const quota = sample?.openrouter;
  const row = (budget: OpenRouterBudget, id: string) => <div className="zai-limit-row" key={id}>
    <strong>{label(budget.scope)} budget · USD{budget.resetInterval ? ' · '+budget.resetInterval : ''}</strong>
    <p>Limit {budget.unlimited ? 'Unlimited' : money(budget.limitUsd)} · Used {money(budget.spendUsd)} · Remaining {money(budget.remainingUsd)}</p>
    <p>{budget.resetsAt ? 'Reset '+new Date(budget.resetsAt).toLocaleString('en-GB', { timeZoneName: 'short' }) : 'Reset time unknown'}</p>
    <p>BYOK usage in this budget: {budget.includeByok === null ? 'Unknown' : budget.includeByok ? 'Included' : 'Excluded'}.</p>
  </div>;
  return <section className="zai-limits" aria-label="OpenRouter key limits">
    <p className="zai-limits-heading">OpenRouter · {sample?.state === 'current' ? 'Reported' : sample?.state === 'stale' ? 'Stale' : 'Unknown'}</p>
    {!quota && <p>Key budgets have not been reported. Missing data does not mean zero remaining.</p>}
    {quota?.selectedBudget && <><p>Current limiting budget · {sample?.remainingPercent == null ? 'Remaining percentage unknown' : new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(sample.remainingPercent)+'% remaining'}</p>{row(quota.selectedBudget, 'selected')}</>}
    {quota?.keyBudget && <details open={!quota.selectedBudget || quota.selectedBudget.scope !== 'key_limit'}><summary>API key cap</summary>{row(quota.keyBudget, 'key')}</details>}
    {!!quota?.budgets.length && <details><summary>All reported budgets</summary>{quota.budgets.map((budget, index) => row(budget, String(index)))}</details>}
    {quota && <p>Reported usage · Today {money(quota.usage.daily)} · This week {money(quota.usage.weekly)} · This month {money(quota.usage.monthly)}.</p>}
    {sample?.checkedAt && <p>Observed {new Date(sample.checkedAt).toLocaleString('en-GB', { timeZoneName: 'short' })} · Source: OpenRouter current API key.</p>}
    <p>Amounts are USD. A key or member budget is a spending cap, not the account’s remaining credit balance. Other clients can use the same budget.</p>
  </section>;
}
