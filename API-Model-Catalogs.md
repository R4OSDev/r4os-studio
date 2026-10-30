# API connections, models and sessions (0.8.14)

System → Settings → LLM Provider offers OpenAI / ChatGPT subscription,
OpenRouter, Custom API and Local API. API settings include the display name,
canonical API prefix, Responses/Chat Completions protocol and optional bearer
key. Local addresses refer to the Studio host. Save and ordinary opening only
read/write local configuration; they never send a model request or check remote
metadata. Existing subscription sign-in, usage and account homes are unchanged.

Keys are write-only. Replace key stages a replacement, Clear key stages removal,
and Cancel changes discards the form and its in-memory key. Removing a bearer
key disables admission. Browser storage keeps only original request IDs,
operation/kind and the original retirement revision, never keys or request
bodies. Read original result reconciles response loss without replay. A404
allows an explicit retry with the same original UUID, after reviewing/re-entering
the settings/key; changed original input conflicts instead of creating another
connection. Retirement closes admission first and retains credentials while an
original model or metadata transport remains unconfirmed.

## Metadata check and cache

Check connection / refresh models explicitly starts one metadata-only GET at
the saved API prefix plus `/models`. No inference endpoint, redirect, generic
proxy, retry, paid probe, automatic model download or fallback target exists.
A successful metadata check confirms its own response only, not individual
model entitlement or actual tool execution.404 explains the exact manual-ID
fallback. Safe auth/account/rate-limit/timeout/format errors expose no raw
provider messages or reflected key values.

The unprivileged coordinator journals the actual metadata operation UUID before
DNS, validates all addresses with the shared public/local endpoint policy and
starts a credential-free waiting Node helper. The exact PID/birth/script and
enabled configuration/credential revision are claimed atomically before the
private bootstrap pipe receives the selected key. Sockets use an exact checked
IP with original SNI/certificate verification, no second DNS lookup. Metadata
credentials stay held through rotation until the helper's exit is confirmed.
Disconnect cancels only original helpers; recovery never repeats their GET.
Malformed/uncertain holds preserve credentials and block final retirement.

Two checks may run concurrently, one per connection. DNS is bounded to10s,
helper bootstrap5s, HTTP inactivity10s and absolute HTTP lifetime15s. Headers
are limited to16KiB, JSON to4MiB and remote entries to256; compressed responses,
invalid UTF8/JSON, duplicate IDs and redirects are rejected. The browser polls
only original receipts for up to32s, then offers an explicit read/recovery.

Model catalogs and their original receipts are published in the same private
SQLite transaction (`model_catalogs` / `catalog_requests`, additive schema1).
Cache reads make no network request. Configuration changes mark older facts
stale. Up to320 entries allow manual IDs beyond the256-entry metadata bound.
Manual facts survive refresh; metadata is truncated before explicit entries.
Same IDs on different provider UUIDs remain independent. An unavailable API
catalog does not disable subscription model choices.

## Explicit model contracts

Generic Models API IDs alone establish no context, tool, streaming or reasoning
capability. OpenRouter's documented architecture, supported_parameters,
context_length and top_provider.max_completion_tokens supply only their actual
facts; its published streaming contract is separate. No effort/default list is
guessed. Every entry shows its source, token limits, declared/effective
capabilities, reasoning levels and reasons preventing agent execution.
[OpenRouter Models API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties),
[streaming contract](https://openrouter.ai/docs/api_reference/streaming).

Add exact model ID / Edit model facts accepts an explicit documented contract.
Text, function tools, streaming and a reasoning/default-effort contract are
required; Chat Completions additionally needs a known context window. A
declared nonreasoning model uses the explicit `none` contract. Unknown stays
unknown. Hosted web/image generation, image input, Fast Mode and native Goal
remain unavailable in these API adapters. Configuration does not verify a real
account/model's entitlement (`runtime: not-qualified`). Provider-specific and
extended lifecycle qualification follows0.8.15–17.

Qualified entries compile a neutral minimal native ModelInfo for pinned
Codex0.163.0. Model prompts, context sizes, efforts and speed tiers are not
borrowed from OpenAI model lists. Explicit context/null and Studio-owned direct
tool/transport policy remain separate. Existing private revision-bound Models
JSON from0.8.12/13 remains a compatibility fallback only when no SQLite catalog
exists. The selected compiled descriptor is frozen into the original admission
and credential lease; no model or metadata request occurs on session creation.

New Session, Session settings and Composer share the project/skill model
choices. Unqualified/stale choices are disabled. API connection/endpoint/
protocol identity stays fixed for a conversation; another provider requires a
new session. Missing models/errors preserve the actual selected value, original
request, message drafts and attachments. No automatic provider/model switch
or conversation conversion is performed.

## Qualification

Nine focused private-store/actual metadata-helper cases as UID996 cover atomic
catalog/receipts, capacity, manual fallback, stale facts, key rotation, unknown
holds, original cancellation/recovery and independent subscription catalogs.
The protected HTTP case includes all new routes and type/coercion boundaries.
Owned TLS/DNS fixtures verify certificate rejection before HTTP, pinned SNI/IP,
mixed metadata DNS rejection, bounds, redirects and reflected-key filtering.
Actual original-binary project/skill workers consume the SQLite-derived neutral
descriptor, perform two acknowledged file writes once each and resume the same
thread; Stop uses the same original runtime. Browser component cases1440/320
cover kinds, optional keys, original response loss/retry, exact manual IDs,
metadata-only checks, keyboard focus and project/skill draft/upload retention.
Build, TypeScript, lint and Python syntax are required before publication.
All fixtures are owned/local, with no real key, model inference or user VM/run.

OpenRouter0.8.15 applies a provider-specific gate: plain streamed Chat/function
tools and its own bearer key. Reasoning tool-history and OpenRouter Responses
remain unavailable; generic/local Responses is unchanged. Optional routing and
attribution, actual origin records and precise errors: [API-OpenRouter.md](API-OpenRouter.md).
