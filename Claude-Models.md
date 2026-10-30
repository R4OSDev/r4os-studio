# Native client model facts and session inputs (0.8.55)

Read native model catalog in the connected Claude provider view uses the same
protected original metadata-request flow as subscription limits. The unchanged
native SDK supplies supportedModels alongside account and quota observations;
auth status is checked before and after it. No model prompt is submitted.
Cached GETs do not invoke the native client.

Each receipt binds provider/account/revision/runtime and preserves the native
aliases and resolved wire identifiers. Duplicate aliases for one resolved ID
share a row; an explicit model label takes precedence over the default label.
The catalog preserves reported effort choices and offers the native default
without inventing a default effort. Unsupported shapes fail without changing
existing selections. Reconnecting a different account cannot reuse its cache.

The pinned ModelInfo exposes neither context-window size nor image support.
Context size remains unknown. A separate hash-pinned Studio input profile in55
qualifies image delivery for authenticated fixed native Claude wire IDs, using
the provider's vision contract and the checked SDK content path. The actual
real-model check uses `claude-haiku-5-5`; it does not assert inference for every
model. The separate capability source stays explicit instead of fabricating a
ModelInfo field.
Fresh catalog receipts are required for that additional capability. See
[Claude-Inputs.md](Claude-Inputs.md). Fast Mode remains unavailable even when the client
advertises it. Client model advertisements are not an independent subscription
entitlement or billing guarantee. Fresh catalogs with a fixed resolved model
ID can qualify text selection through `shared/claude-text-profile.json`.
That Studio adapter profile is bound to the exact unchanged runtime/SDK hashes;
it does not rewrite the installed offline foundation profile or native files.
Older catalog receipts never acquire eligibility merely through an update.
The original Codex/API provider selection and engine boundaries remain intact.

New project and skill sessions use the selected provider's runtime availability.
An unavailable Codex installation does not block an available native Claude
runtime. Reasoning offers a visible, valid Native default choice, including
the empty effort value at the HTTP boundary. All effort values are still
validated against the native catalog. Existing conversations cannot change
engine or native account; choose another provider in a new conversation.

Native Studio prompts/project instructions/skill snapshots retain the existing
frozen input path and an explicit native source hash. Documents and qualified
images use the native content contract. Unqualified attachments are refused rather than discarded.
If a tool captures a screenshot for a model with unqualified image delivery,
the original result stays intact and a separate model-visible notice explains
that capture does not prove visual inspection.

Actual isolated native metadata checks with a synthetic account and owned TLS
endpoint prove canonical IDs, alias handling, effort metadata and original
receipt/cache behavior with zero model or mutation requests. They do not prove
real account entitlement or unreported image/context capabilities. Focused
tests also cover an account change, unavailable-model creation refusal, image
delivery notice, protected HTTP and the actual React UI at 1440/320px.

Selection alone grants no inference. Before every original send, queued
follow-up or bounded Goal step the worker checks its original credential
lease, native first-party Pro/Max authentication, SDK account, fresh quota
windows and explicitly disabled extra usage. Catalog, account, canonical
model, effort and adapter profile must match the frozen request. Unknown or
exhausted quota blocks admission. Account settings are never changed by Studio.
Native fallback models are disabled and the observed model must exactly match
the selection before a Studio tool can run. No zero-cost guarantee is inferred
from a client-side list-price estimate.

New original text sends request native input echoes, as queued/Goal inputs
already did. The native UUID and exact text hash must match the original
request/config/worker/history before a tool effect is admitted. One immutable
input receipt is retained; missing acknowledgement leaves an uncertain send
protected rather than replaying it. The provider record's legacy `enabled`
field remains false for compatibility; eligibility belongs to the new catalog
receipt and each fresh admission, not that foundation-era flag.

The production admission path is qualified with the unchanged SDK/CLI against
an owned TLS endpoint and synthetic native account, without replacing the
admission decision. This proves the protocol, not real subscription entitlement.
Shared creation/settings/composer views are checked at1440/320px for project
and skill scopes, including missing Codex and native default reasoning.
Actual account acceptance and the remaining Goal/live/direct/retry/lifecycle
work are recorded separately; this release does not claim complete0.8.22/23.
