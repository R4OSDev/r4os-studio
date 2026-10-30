# Native client model facts (0.8.22, partial implementation)

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
Those facts remain unknown. Fast Mode remains unavailable even when the client
advertises it. Client model advertisements are not an independent subscription
entitlement or billing guarantee. The provider and session selectors explicitly
show execution as unavailable; server validation also refuses these models.
The original Codex/API provider selection and engine boundaries remain intact.

Native Studio prompts/project instructions/skill snapshots retain the existing
frozen input path. Unqualified attachments are refused rather than discarded.
If a tool captures a screenshot for a model with unqualified image delivery,
the original result stays intact and a separate model-visible notice explains
that capture does not prove visual inspection.

Actual isolated native metadata checks with a synthetic account and owned TLS
endpoint prove canonical IDs, alias handling, effort metadata and original
receipt/cache behavior with zero model or mutation requests. They do not prove
real account entitlement or unreported image/context capabilities. Focused
tests also cover an account change, unavailable-model creation refusal, image
delivery notice, protected HTTP and the actual React UI at 1440/320px.

This is the catalog/input boundary, not completed model execution. All 0.8.22
tasks and acceptance remain open for their remaining positive execution and
capability qualification. The closed production model-admission default,
shared-limit/overage guards and final lifecycle work remain separate open
stages. No existing conversation is migrated to a different engine.
