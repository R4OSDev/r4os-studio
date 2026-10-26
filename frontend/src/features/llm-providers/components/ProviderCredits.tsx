import type { CreditBalance, CreditUsageControl, UsageLimit } from '../../../../../shared/llm-providers';

/** Equal reported snapshots share a display; balances are never added. */
export function creditGroups(limits: UsageLimit[]): { names: string[]; credits: CreditBalance }[] {
  const groups = new Map<string, { names: string[]; credits: CreditBalance }>();
  for (const limit of limits) {
    if (!limit.credits) continue;
    const credits = limit.credits, key = JSON.stringify([credits.hasCredits, credits.unlimited, credits.balance]);
    const group = groups.get(key);
    if (group) { if (!group.names.includes(limit.name)) group.names.push(limit.name); }
    else groups.set(key, { names: [limit.name], credits });
  }
  return [...groups.values()];
}
export function creditAvailability(value: CreditBalance): string {
  return value.unlimited === true ? 'Unlimited' : value.hasCredits === true ? 'Available' : value.hasCredits === false ? 'Unavailable' : 'Not reported';
}
export function ProviderCredits({ limits, stale, control }: { limits: UsageLimit[]; stale: boolean; control?: CreditUsageControl }) {
  const groups = creditGroups(limits);
  return <section className="usage-credits" aria-label="Credits"><h3>Credits</h3>
    <p className="field-help">Codex credit balances, separate from earned resets. Identical reported balances are shown once.</p>
    {stale && <p className="provider-alert" role="status">Previously loaded credits may be out of date.</p>}
    {groups.length ? groups.map(({ names, credits }, index) => <article className="credit-balance" key={index}>
      <h4>{names.join(', ')}</h4><dl><div><dt>Balance</dt><dd className="credit-amount">{credits.balance ?? 'Not reported'}</dd></div><div><dt>Availability</dt><dd>{creditAvailability(credits)}</dd></div></dl>
    </article>) : <p className="field-help">OpenAI did not report credits for this account.</p>}
    <p className="field-help">Read-only. {control?.supported === false ? 'Spending controls are not available through this connection. Viewing credits does not change spending settings.' : 'A reported balance does not indicate whether credit spending is enabled.'}</p>
  </section>;
}
