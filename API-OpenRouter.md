# OpenRouter provider (0.8.15)

New Provider → OpenRouter starts with `https://openrouter.ai/api/v1`, its own
bearer key and Chat Completions. Save/open performs no inference or remote
metadata check. A key may be configured later; a usable model connection needs
that key. Subscription credentials are never reused. Generic/local API
Responses and Chat adapters remain independent.

## Qualified scope

This release qualifies streamed **plain text and function tools over Chat
Completions**, full local history and same-thread native resume. Explicit
text/function/stream/context and nonreasoning model facts are required. Missing
facts remain unknown; configuration is not proof of remote account entitlement.

OpenRouter Responses, reasoning tool-history, image input, hosted web/image,
native Goal and Fast Mode are unavailable in this provider scope. Signed or
encrypted reasoning is not discarded as a compatibility shortcut. Unsupported
history/deltas fail before an invalid tool prefix is released. OpenRouter
requires reasoning-block continuity for tool calls.
[Reasoning contract](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

The chosen model path is `/chat/completions`; metadata uses `/models`.
`/responses` is published by the provider but not qualified by this release.
The native Responses envelope maps explicitly to documented Chat roles,
text/function declarations and original call IDs/results. Native telemetry stays
local. Its `store:false` directive maps to stateless full-history Chat input,
without an undocumented `store` field; this does not control remote logging.
Documented prompt_cache_key, service_tier(default) and stream_options(include_usage)
are retained.
[Chat API](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion).

## Explicit routing and attribution

Settings allow16 exact preferred and16 exact allowed provider slugs, each at
most120 characters. An allowlist must include every preferred slug. Backend
fallbacks default off and require an explicit checkbox. The adapter fixes
`provider.require_parameters:true`: unsupported tool parameters must not be
silently ignored. No arbitrary provider JSON, headers, model list or transform
plugin enters this policy. The selected model ID stays fixed. Gateway backend
routing is separate from a Studio model/provider change or client retry.
[Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

Share app attribution stages a paired HTTP/HTTPS URL and ASCII title for
OpenRouter's app rankings/analytics. Only the saved `HTTP-Referer` and
`X-OpenRouter-Title` headers are emitted. They do not come from browser Origin,
credentials or the current page. Cancel discards key and routing drafts.
[App attribution](https://openrouter.ai/docs/app-attribution).

Policy is frozen into the original configuration revision, metadata binding
and admitted/queued Run. Rotation affects future admissions; original leases
retain their key/policy. Reading an old record without a policy supplies safe
defaults without disk migration. The relay revalidates it inside the existing
checked-IP/TLS/SNI/redirect/time/size boundary.

## Provenance and errors

The relay opts into `X-OpenRouter-Metadata: enabled`. Requested model, declared
response model/backend, selected endpoint labels, provider response ID and local
transport ID remain separate. Gateway attempt/strategy are optional; missing
values are unknown. Different endpoint/frame naming is preserved. Raw summaries
or pipelines are not copied. An attempt above1 conflicts with a no-fallback
policy. Reported integer token counters are validated; missing usage stays absent.
[Router metadata](https://openrouter.ai/docs/guides/features/router-metadata).

A bounded private stdout channel captures256 origin observations per Run,
validated against its requested model/sequence. After transport closure the
worker writes notice items with structured `apiOrigin`. These diagnostics are
not native conversation input, tool receipts or billing identities. Diagnostic
loss cannot replay model/tool operations.

API401 identifies the key,402 credits/billing,403 access,429 rate limits and503
temporary unavailability. Safe numeric mid-stream categories preserve uncertainty;
raw provider text/URLs/reflected keys are never shown. A temporary candidate is
not retry authorization. Subscription messages are unchanged. Automatic recovery
0.8.10 remains separate.

## Qualification

Two Node protocol groups, four Python policy/error groups and the protected
HTTP case cover strict fields, atomic edits, old-record reads, immutable policy,
capability gates, numeric errors and origin/usage distinctions. Eight actual
original-native UID996 fixtures use an owned TLS endpoint in an empty network
namespace: project/skill, HTTP401/402/429/503, missing DONE and Stop. Positives
perform two file writes once each, resume the same thread and retain distinct
origins. Each negative makes one POST with no uncertain tool-prefix execution.
Metadata TLS/DNS/bounds fixtures and browser1440/320 routing/key/Cancel/focus/
no-probe cases pass. Required build/TypeScript/lint checks precede publication.

The public Models API was read once without a key on2026-10-30 for schema
research:456 entries/768363 bytes at the recorded SHA. No static name list is
imported. Metadata remains bounded to256 entries plus manual entries; an exact
manual ID covers models outside the cache.
[Public Models API](https://openrouter.ai/api/v1/models).
No real key, paid/model inference, production provider mutation or user agent/VM
action is used. See [API-Providers.md](API-Providers.md) and
[API-Model-Catalogs.md](API-Model-Catalogs.md).
