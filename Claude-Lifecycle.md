# Native Claude lifecycle (0.8.23, partial)

The private bounded Studio GOAL engine is qualified separately in
[Claude-Goal.md](Claude-Goal.md). It preserves the original Play and native
session, with fresh admission per step. Public Goal controls/live activation
remain gated pending their separate adapter and actual account acceptance.

Stop closes tool admission before requesting the native interrupt. Studio drains
the original terminal result before closing the query. A confirmed result and
readable, unchanged native history permit a later explicit resume on the same
UUID. An acknowledgement or process exit alone never proves a readable result.

Before each explicit send, the native SDK reads subscription usage with
`skipBehaviors: true` and refreshes account information. A fixed, network-isolated
native auth-status command independently confirms the same account, plan and
first-party authentication. The observations, original lease, canonical model,
catalog request and selected effort must still match. Missing/stale server
meters, exhausted windows or extra usage enabled/unknown deny input. There is
no qualified per-send overage switch: account extra usage must actually be
disabled and stay disabled. The adapter never enables it or switches to API
billing or another model.

Limit/overage events persist a hold keyed by verified account identity, shared
across provider entries for that account. Metadata reads and reset clocks cannot
clear it. A new explicit send needs fresh positive admission; compare-and-swap
release preserves any concurrent newer rejection. A warning is an observation,
not proof that the original model execution failed. Already admitted effects
and their original result remain subject to normal confirmation.

If admission denied input and the native process positively closes, the original
request, zero submitted prompts, zero tool intents and byte-identical history
allow revoking that unused opening. This preserves the original session UUID;
it does not replay input or repair an unknown model execution.

Original result UUIDs bind private numeric usage receipts to runtime, session,
run and Studio request. Conflicting duplicate receipts fail without changing
the original. Main-loop usage and cumulative model snapshots retain different
source semantics. Cumulative/resumed values are never summed as turn totals;
native list-price estimates are separate from quota and actual billing.
Input/cache statistics and lifetime retention are implemented in0.8.46 through
completed response IDs and the common numeric outbox. Output/total accounting
remains unqualified. Details: [Claude-Input-Usage.md](Claude-Input-Usage.md).
Session cleanup removes private snapshots through the existing scoped deletion
mechanism while retaining the numeric lifetime receipts.

The SDK has no qualified native Codex GOAL interface. Claude GOAL and direct
steering remain unavailable pending bounded orchestration and their original
receipts/budgets. Text queues and native input acknowledgements are integrated
in0.8.47; see [Claude-Queue.md](Claude-Queue.md). No Codex
GOAL RPC, automatic retry, restore inference or automatic Play is substituted.
Public Claude model execution remains disabled by the existing catalog gate.

Focused tests and the actual unchanged pinned SDK/CLI in closed filesystem and
network namespaces cover admission, extra usage/unknown/exhausted refusal,
common tool dispatch, confirmed Stop and explicit same-history resume.
Credentials, model endpoint and quota responses in these checks are owned
synthetic fixtures. They do not establish a real account subscription,
entitlement, billing guarantee or complete GOAL/queue/statistics integration.
All 0.8.23 tasks and its overall acceptance remain open for those missing parts.
