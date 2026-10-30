# Native Responses transport (0.8.12)

API sessions can use the pinned, unmodified Codex0.163.0 binary through a
run-owned Responses relay. The browser renders the existing items/deltas and
uses the existing Send, queue, receipt and Stop APIs. The unprivileged worker
owns native conversation persistence, the model process and its transport.
There is one native agent/tool loop; the relay does not run an agent.

## Admission and model identity

A new API session records its connection UUID, canonical base URL and protocol
in `engine.api`. Moving an existing conversation between subscription and API
providers, API UUIDs, endpoints or protocols requires a new session. No account
home, conversation or global default model is migrated. New API sessions keep
native hosted web search, image generation, Fast Mode and Goal controls off:
these capabilities need their own qualification. Ordinary Studio tool rights
and their existing schema/permission/result broker remain in force.

Model metadata must already be qualified for that configuration revision.
`ApiProviders/Models/<provider UUID>.json` is a private0700/0600 internal catalog
with `{schema:1, providerId, configRevision, models}`; models use the pinned
binary's rich native catalog schema. It currently permits text input and
Responses without Responses Lite. Missing, stale or unsupported metadata does
not invent a context window, tool capability or reasoning mode. Catalog
discovery/writing, provider UI and per-model capability reporting are later
roadmap entries0.8.14–0.8.17. A configured connection is not proof of remote
availability or entitlement; the public record retains `runtime:not-qualified`.

Admission freezes public config/credential revisions and selected native model
metadata into the original run snapshot. A deterministic UUID derived from
owner/session/original request is the actual future Run ID, including queued
input. An atomic API-store reservation retains its credential revision before
the session transaction commits. A changed reservation cannot replace an old
intent. A rare failed session commit may retain a protected unclaimed
reservation; reading it never starts inference. Explicit disconnect closes
admission and safely releases never-claimed reservations under the same lock.

The original worker claims that reservation with its PID, process birth and
release before starting transport. Rotation preserves the frozen revision for
an admitted run; future admissions require current settings/catalog metadata.
Disconnect cannot race a new claim after closing admission. Claimed/unknown
leases retain credentials until closure is proved; an unconfirmed lease blocks
retirement rather than discarding keys or replaying work.

## Credential and socket boundary

The API secret database is never mounted into native or tool namespaces. Native
uses a session-owned `Codex/ApiHome` and the existing session-owned rollout/state
directories. Only the trusted relay receives the selected real key through a
private bootstrap pipe. Its model process gets an unrelated random relay nonce
from a readonly0600 file through a tiny launcher, not a key or nonce in argv.
The existing tool/terminal namespace has neither home, secret, nonce nor network
access. Normal cleanup closes both native and relay processes before releasing
the exact original credential lease. Unconfirmed closure retains the lease.

The relay listens on a random127.0.0.1 port, requires that nonce, and accepts only
POST `/v1/responses` with the frozen model. It forwards exactly one POST to the
canonical configured prefix plus `/responses`, with a fresh fixed header set.
No cookies, caller headers, redirect Location, provider error text or provider
request IDs are forwarded. Bounded non-success errors retain only allowlisted
codes and fixed descriptions. Public DNS resolves once per run; all returned
addresses must pass scope validation before Node starts. The actual connection
uses an exact checked IP with the original TLS hostname/SNI and certificate
verification. There is no DNS lookup between validation and connect, redirect
following, retry or alternate endpoint. Explicit local IP/localhost services
remain subject to the endpoint policy in API-Providers.md.

Headers are limited to16KiB, model request JSON to8MiB, stream bytes to16MiB,
error bodies to64KiB, connection establishment to10s and upstream inactivity to
300s. Backpressure bounds buffered stream data. Compression, wrong response
content type and oversized responses fail explicitly. Stop/worker-pipe closure
closes upstream sockets; truncated streams never receive an invented completion.

## Context, tools and failure

The pinned binary sends the complete active local conversation/tool context with
`store:false`, streaming and no nonempty `previous_response_id`/conversation ID.
WebSockets, Responses Lite and native HTTP/stream retries are disabled for this
private provider. No ID is stripped from a delta-only request. This full-context
mode also works with a stateful-capable Responses endpoint; provider retention
is not used. Incremental stateful/store:true mode is not offered. OpenRouter and
Ollama stateless contracts therefore receive their complete input each time.

Native events feed the existing durable Studio items/deltas. Only complete
validated function arguments reach the existing broker. Original call IDs and
confirmed tool results survive restart; a repeated call with the same ID and
arguments returns its stored receipt. Interrupted/failed inference does not
erase that effect. There is no extra model request on browser reconnect or lost
completion. A native start/resume failure preserves its files and does not
materialize a replacement thread. Context-limit errors and missing stream
semantics terminate the original run without fallback. Automatic temporary
provider-error recovery remains the separate, unfinished0.8.10 controller work.
Native local compaction uses another ordinary full-context Responses request and
persists its own summary/checkpoint; it does not use `/responses/compact` or
server-retained context. A forced compaction after one acknowledged write and
resume from its saved checkpoint are qualified separately. Older raw rollout
records and the Studio tool ledger remain stored. An endpoint/model unable to
produce the required summary must fail; the relay supplies no synthetic summary
or compaction fallback.

## Qualification

Original binary SHA256:
`399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`.
Source revision: `83086188ae0614bd882818ff1aa23f3194962012`.
Local source inspection establishes the full-input/store:false request and
custom-provider fields; original-binary offline fixtures establish behavior.

Six actual Studio-worker fixtures cover new project/skill API sessions,
character deltas, split function arguments, real file sandbox/ledger, repeated
call IDs, original-thread resume, queued frozen input, Stop, context rejection
native context compaction with original-thread resume and lost completion after
an acknowledged write. The project receiver rejects
stateful requests; a separate skill receiver demonstrates retention then uses
the same full-context native flow. Component metadata and snapshot socket paths
are fixture-local; no user project/VM or real model is involved.

Nine private-store cases include concurrent/atomic revisions, key masking,
protected storage, admission/claim/rotation, closed admission and held unknown
leases. A separate offline TLS fixture uses an owned loopback alias and a
temporary test CA to prove certificate rejection before HTTP, verified original
SNI, fixed checked IP, mixed public/metadata DNS rejection, no redirect/key
forwarding, invalid requests before upstream, safe context errors and byte/
header/encoding bounds. Two existing queue/deletion cases also pass. No system CA, production provider, real API key, paid
inference or user's session is used or changed.

Primary provider references:
[OpenRouter Responses](https://openrouter.ai/docs/api_reference/responses/overview),
[Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).
Capability/entitlement qualification of a real account/model is not inferred
from these protocol fixtures. Chat Completions translation is added in0.8.13; see
[API-Chat-Completions.md](API-Chat-Completions.md).
