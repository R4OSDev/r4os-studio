# Chat Completions transport (0.8.13)

Qualified Chat-Completions-only endpoints use the same unmodified native
Codex0.163.0 runtime, original session history and Studio tool broker as
Responses. A private host relay translates wire messages and SSE events.
It has no agent, tool dispatcher, context controller or Goal loop. The browser
continues to read the existing Studio items/deltas and original receipts.

## Qualification before admission

The API connection/session retains its original UUID, base URL and protocol;
changing identity requires a new session. Exact config/credential/model
revisions and original Run/worker leases follow API-Providers.md. Real keys
remain in the trusted relay; native gets its private unrelated nonce and tools
retain their separate network/credential-free namespace. Host capability
`apiChat:1` and a compatible immutable worker release are required.

The revision-bound internal catalog must contain a qualified rich native model
plus this private policy:

```json
{
  "studio_chat": {
    "schema": 1,
    "systemRole": "system",
    "reasoning": "none",
    "functionTools": true,
    "streaming": true
  }
}
```

`systemRole` may be system/developer and reasoning may be none/effort. Text input,
known positive context window, function/stream support, no verbosity parameter,
no reasoning-summary parameter and no required opaque reasoning replay must be
qualified. None mode requires the explicit none effort; effort mode forwards
the selected standard reasoning_effort without claiming signed/provider-specific
reasoning history. The policy is frozen separately as apiChat and removed from
the rich catalog passed to native. Missing/unrepresentable capabilities fail
before a Run or credential reservation is created. No guessed model capability,
context window or substitute inference is used.

Model discovery/settings UI and neutral descriptors from explicit facts are
provided by0.8.14 ([API-Model-Catalogs.md](API-Model-Catalogs.md)). Real account/model
and extended lifecycle qualification follows0.8.15–17. Public connection records still describe configuration,
not remote qualification. Image input/generation, hosted web, Fast Mode and
native Goal execution are not qualified for these API sessions. Proprietary
provider protocols, opaque reasoning, extension deltas, unsupported structured
text output and non-text history fail explicitly rather than losing content.

## Wire mapping

| Native Responses input | Chat Completions representation |
| --- | --- |
| Complete active local context | Complete messages array, no previous response ID |
| Developer instructions | Qualified system/developer role, preserving priority over user input |
| Text content parts | Ordered text parts with every text value retained |
| Function declarations | tools[].function with original name/schema/strict flag |
| Function calls/results | Assistant tool_calls and tool messages with original call IDs |
| Selected supported effort | reasoning_effort; none consumes the declared no-reasoning policy |
| store/stream/tool choice/parallel flag/cache key/default tier | Explicit corresponding Chat fields |
| Native private client_metadata | Bounded local adapter metadata, echoed in private response metadata |

Distinct native system/developer priorities are not collapsed if both occur and
the endpoint only accepts system. Historical function calls remain representable
during native compaction even when the current request exposes no tools. Every
historical call must have its matched result; no orphan result or unresolved
call is discarded. Optional encrypted-reasoning include is unavailable for this
declared non-replay protocol; actual opaque history or extension output is
rejected. Private native telemetry is not truncated into Chat's constrained
model metadata. Generation controls and conversation content are not deleted
to make a rejected provider request succeed.

The upstream operation is exactly one POST to the canonical configured prefix
plus `/chat/completions`, using the checked-IP/TLS/Origin/nonce boundary shared
with Responses. No redirect, retry, alternate target or second agent loop is
introduced. Reconnect reads existing events. Endpoint dialects must accept the
qualified emitted fields; rejecting a parameter does not cause another POST
with that parameter silently removed.

## Streaming and completion

The incremental SSE decoder handles UTF8 byte boundaries, split UTF16 text
surrogates, CR/LF/CRLF, comments, multiline data fields, empty-choice usage chunks
and OpenRouter's repeated final finish choice. Parallel indexed function
name/argument deltas are collected separately; IDs must remain stable once
announced. Every call in the completed set must have a known function, original
unique call ID and complete valid object arguments before any call is released.
The existing broker then enforces the frozen schema/rights/original receipt.
Malformed later arguments cannot release an earlier valid tool prefix.

Text deltas can stream immediately. Functions/completion are emitted only after
a valid finish reason and framed [DONE]. Lost final, malformed JSON/usage/IDs,
unknown extensions or provider errors do not invent a completion or replay work.
Length/filter finishes produce terminal incomplete responses with reported
usage, without releasing pending tools. The filter reason is namespaced as
studio_chat_content_filter: this preserves the blocked outcome and avoids
Codex0.163.0's separate retry treatment of the literal content_filter category.
Actual provider finish reason remains separate adapter metadata. Known failure
codes receive fixed Studio descriptions; provider text/URLs/credentials do not.

Native response IDs beginning studio_chat_ are local transport identities.
Provider response IDs are recorded separately when actually reported; absent
IDs are not invented. Only reported nonnegative integer usage/cached/reasoning
fields are mapped; absent usage remains absent. Native local summary compaction
and same-thread resume use the same translated context with their original
saved checkpoint and Studio tool ledger. No synthetic summary is supplied.

Limits:16KiB headers,8MiB inbound/translated request,16MiB stream,512KiB SSE event,
8192 history items,128 declarations,32 parallel calls,128KiB per argument object,
64 nesting levels/65536 JSON nodes and196608 UTF8 text bytes. Connect timeout10s,
inactivity300s and absolute HTTP request deadline900s apply. The deadline also
adds a finite whole-request bound to the shared Responses relay. Stop/parent
closure destroys owned sockets; unconfirmed closure retains original leases.

## Evidence and limits

Four grouped protocol cases exercise faithful context/parameter/ID mapping,
UTF/SSE fragmentation, interleaved calls, malformed/lost streams, usage/finish
variants and bounds. Eleven private-store/qualification cases include missing
capabilities before admission. Ten actual Studio-worker/original-binary offline
fixtures as UID996 cover project/skill, two actual parallel file writes once
each, repeated IDs across restart, standard effort, compaction/checkpoint resume,
bad arguments, missing DONE, quota, length, filter, Stop and deadline. The last
fixture accelerates only the900000ms relay deadline through a test-only Node
preload; production source/timers and the native binary are unchanged. An
original Responses core/restart probe checks the shared transport path.

Fixture component metadata/socket paths are local; the actual Studio ledger,
file sandbox, native RPC and relay run normally. No production provider, real
key, external model/paid inference, user session/VM or project pins are changed.
Fixtures establish protocol/lifecycle support, not compatibility or entitlement
for every model advertised by an API provider. Automatic provider-error recovery
remains the separate unfinished0.8.10 controller.

Primary references: pinned Codex source83086188ae0614bd882818ff1aa23f3194962012;
[OpenRouter streaming](https://openrouter.ai/docs/api_reference/streaming),
[Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).
