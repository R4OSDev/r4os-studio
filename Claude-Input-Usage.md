# Claude input/cache statistics (0.8.46, partial lifecycle)

The pinned SDK0.3.312/CLI2.1.312 worker now publishes completed main-loop
response input/cache counters through Studio's numeric statistics outbox.
Session, project and lifetime views use the existing common totals and coverage.

Anthropic documents per-step input/cache values and deduplication by the
provider message ID. Assistant output counters can be placeholders, while
result/model snapshots have different cumulative scopes. Those values are
excluded from this input projection. References:
[cost and usage](https://code.claude.com/docs/en/agent-sdk/cost-tracking),
[SDK types](https://code.claude.com/docs/en/agent-sdk/typescript).

The private Node projection forwards three safe input counters and a fixed
error marker, with absent/invalid counters represented as unknown. The tracker
requires the original native response boundary. It retains identities and
numbers only, without duplicating text, images or tool arguments in memory.
Synthetic error messages and subagent frames cannot contribute input totals.
An interrupted response with a native closing boundary may retain its confirmed
input counters; it does not establish output completion or billed amounts.

The normalized input count includes uncached input plus cache creation and cache
read tokens, and is available only when all three counters are known. Cache
counters remain separate. Output, total and reasoning counts remain unknown.
Zero is retained only when explicitly reported as a valid counter. Missing
fields are not replaced with zero. Partial coverage stays visible.

The receipt key binds owner, Studio/native session, provider message ID and both
native/SDK pins. Multiple blocks or replayed messages after explicit resume use
the same key. Conflicting values preserve the first receipt and mark incomplete
coverage. The durable numeric outbox precedes the optional private audit link;
an interruption between them cannot lose or double the aggregate. Global
receipts contain only hashes/numbers. Existing scoped session/project deletion
retains pending numeric receipts while deleting private source data.

Four focused Python cases, the existing cumulative-receipt case and eight Node
cases passed. An owned network/filesystem-isolated run used the actual unchanged
SDK/CLI, three distinct fake endpoint response IDs, confirmed Stop and explicit
same-session resume. It produced exactly60input tokens, zero reported cache
tokens and unknown output/total; repeated reconciliation preserved the result.
One original fixture tool effect occurred once. These are controlled protocol
observations, not real subscription, entitlement, quota or billing evidence.

Public Claude model admission remains gated. GOAL orchestration, queued/direct
handoff, output/total accounting and actual account acceptance remain open in
0.8.19/21–23. No user account, session, VM or provider configuration was changed.
