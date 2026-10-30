# API provider configuration (0.8.11–0.8.12)

This is the configuration/credential foundation for OpenRouter, other
OpenAI-compatible services and explicit local model servers. Existing OpenAI
subscription records, account homes and threads retain their original format.
API connections have a separate UUID, name, kind, canonical base URL,
Responses/Chat Completions protocol, none/bearer auth, configuration revision
and credential revision. Public responses expose `keyConfigured`, never a key.

**Responses transport is qualified in0.8.12** for the pinned native binary and
revision-bound internal model catalogs; see [API-Responses.md](API-Responses.md).
API records still report `runtime: "not-qualified"`: configuration is not a
verified remote account/model entitlement. Model discovery and settings UI are
later roadmap entries; no real provider was probed. Chat Completions translation is qualified in0.8.13 through
[API-Chat-Completions.md](API-Chat-Completions.md). Existing subscription sessions are not converted.

## Browser and host responsibilities

The browser/settings API manages explicit connections. The unprivileged agent
coordinator owns their private storage through fixed Unix-socket operations.
No caller-supplied filesystem path, generic HTTP proxy or key-reading operation
exists. The normal provider browser session, allowed Host/same Origin and CSRF
protect mutations. API bodies are bounded to16KiB. Unknown fields and wrong
types are rejected before schema coercion. Existing subscription routes stay
available if the new coordinator capability is unavailable.

Bootstrap auth with GET `/api/providers/`. The following paths are relative to
`/api/providers/api-connections`:

| Method / path | Behavior |
| --- | --- |
| GET (base) | List configured API connections, no store creation on an empty host |
| POST (base) | Create with original requestId, name, kind, baseUrl, protocol, auth and optional write-only key |
| GET /id | Read masked configuration; deleted IDs return410 |
| PATCH /id | Revision-checked changes; key replaces, null removes |
| GET /id/requests/requestId | Read the original masked result or pending retirement; never sends/cancels work |
| POST /id/disconnect | Close admission, stop only that provider's original agent workers, remove credentials after confirmed closure |
| DELETE /id | The same closure plus a retired-ID tombstone |

Original request IDs retain masked results. Repeating one with different input
is a conflict. A frontend must retain only the request ID/redacted metadata;
never persist the key in local/session storage, URLs or logs. On lost response,
read the original receipt before offering an explicit retry. No new provider is
created merely because a prior create result belongs to a deleted ID.

## Private storage and revision lifetime

Storage is under the configured LLMProvider root:

```text
ApiProviders/                         0700
  Providers.sqlite                   0600, public configuration/revisions/receipts/leases
  Private/                           0700
    Secrets.sqlite                   0600, credential values by provider/revision
```

Both files belong to the fixed service user/group and share one local
filesystem. One ATTACH transaction with DELETE journals and FULL synchronization
updates config and secret revisions together. Secrets use secure_delete for
removed SQLite cells. This is logical credential removal, not a claim about
forensic erasure of storage snapshots. Invalid ownership/modes, hardlinks,
symlinks, sidecars or unsupported databases fail closed without chmod/reset.

Changing origin requires an explicitly replaced or removed key. Config and
credential revisions are distinct; updates affect future admissions. Public
immutable configuration revisions and active/unknown original leases retain the
old binding. Rotation removes unleased old credentials. Unknown leases block
final disconnect/removal and retain their original credentials. A disconnect
closes admission before cancellation and preserves a pending original request
if worker closure cannot be confirmed. Read/reconnect never retries the effect.

0.8.12 reserves exact Run/session/owner/request bindings at normal or queued
admission and claims them with the original worker PID/birth/release. Rotation
retains the selected revision; Stop closes native/relay before release. Queue
cancellation releases its never-started reservation; session deletion refuses
held API admissions/transports so unconfirmed evidence survives. Disconnect
atomically closes admission before releasing unclaimed reservations and stopping
original active workers. Unknown/malformed leases remain protected. The shared
secret database is never mounted into a model or tool namespace. Only that
lease's selected credential enters the trusted relay's private bootstrap pipe;
the model gets an unrelated local nonce. No key enters Run/config/worker JSON,
argv, model input, browser SSE or the tool environment. Subscription credentials
are never reused for an API provider. See API-Responses.md for lifetime limits.

## Endpoint and transport boundary

Public APIs require HTTPS. Explicit local connections accept HTTP/HTTPS to
literal RFC1918/ULA/loopback addresses or localhost, resolved as the Studio host.
Local hostnames other than localhost are not yet accepted. Ports and canonical
API prefixes are retained. URL credentials, query/fragment, controls, encoded or
dot-segment paths, link-local/metadata/multicast/unspecified targets, IPv4-mapped
aliases and known local control/database/Studio ports are rejected.

Public DNS names are configuration only. Before any credential-bearing socket,
`resolved_addresses` must validate all resolved addresses against that endpoint's
scope. The transport must connect to an exact checked IP, preserve the original
TLS server name/certificate verification and reject redirects or a fresh DNS
lookup between check and connect. Only fixed model API operations may use the
bound API prefix. Request, JSON/SSE/tool-argument and time bounds must be enforced
by the qualified transport. The actual Responses relay now enforces and checks
these boundaries in0.8.12, including verified TLS and fixed-IP sockets; Chat
Completions translation is separately qualified in0.8.13 with the same boundary.

## Checks

Nine isolated Python cases run as the actual unprivileged service user cover
masked persistence, same-request/stale/concurrent edits, origin/key boundaries,
rollback across both databases, protected paths/modes, held revision leases and
original disconnect recovery, API admission/rotation/claim and queue/deletion
lifetime guards. Two existing queue/deletion cases also pass. One new HTTP case and fourteen existing provider
cases cover auth/Host/Origin/CSRF, bounded schemas, secret masking and unchanged
subscription sign-in/usage/disconnect behavior. No real API key, model request,
user session/VM action or production provider mutation is used.
