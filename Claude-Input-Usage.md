# Claude token statistics (0.8.46/0.8.50, partial lifecycle)

The pinned SDK0.3.312/CLI2.1.312 worker publishes completed main-loop response
input/cache counters and qualified final stream output through Studio's numeric
statistics outbox. Input/cache receipts were introduced in0.8.46; final output
and matching response totals are added in0.8.50.
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
counters remain separate. Without the final output source below, output and
total remain unknown. Reasoning counts are not qualified.
Zero is retained only when explicitly reported as a valid counter. Missing
fields are not replaced with zero. Partial coverage stays visible.

## Final response output (0.8.50)

The private projection forwards only a valid `message_delta` output counter and
known terminal stop reason. The tracker requires that final observation and
`message_stop` on the original native session, matched to a completed main-loop
provider response. Intermediate counts, missing final values, invalid/decreasing
counters, foreign streams and incomplete responses do not establish final output.
Per-response accounting is bounded and retains only identities and numbers.

A separate immutable output receipt is keyed by the original input receipt,
which already binds owner, Studio/native session, provider message ID and runtime
pins. It adds output once and a matching response total only when all normalized
input counters are known. It never adds input again or rewrites earlier input
receipts. Replay after resume or reconciliation deduplicates under that same key;
conflicting values preserve the original and expose incomplete coverage.

This source follows the documented stream output boundary rather than assistant
placeholders or cumulative result/model snapshots. Reference:
[Claude usage scopes and output](https://code.claude.com/docs/en/agent-sdk/cost-tracking).
Totals cover only responses with complete matching measurements. Historical or
interrupted responses can contribute known input while their output/total stays
unknown; aggregate partial coverage remains visible. Reasoning output, native
Goal token budgets, subscription quota and actual invoices are not inferred.

Session cleanup removes both private input/output links through exact session
membership. Common pending numeric receipts survive unavailable aggregate storage
and private cleanup; later delivery does not count them twice. Provider credentials
contain none of these numeric receipts.

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
One original fixture tool effect occurred once. That historical0.8.46 proof
retained unknown output. These are controlled protocol observations, not real
subscription, entitlement, quota or billing evidence.

Additional0.8.50 cases cover final/zero/missing/decreasing/conflicting counters,
response replay, actual scoped session deletion and retained numeric delivery.
An unchanged native SDK/CLI Goal run records four completed response IDs across
two steps:80input,32output and112matching total tokens, one original Play clock
and one file effect. Reconciliation preserves the values. Synthetic auth and
an owned Messages endpoint remain separate from real subscription acceptance.

Public Claude model admission remains gated. Live Goal activation, direct/retry
handoff and overall account acceptance remain open in0.8.19/21–23. The user
explicitly deferred real account acceptance. No user account, session, VM or
provider configuration was changed.
