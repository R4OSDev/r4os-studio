# Full input counting

New inputs accepted from 0.12.22 freeze context-policy schema 4 and the counting
profile alongside the resolved global/session limit. Existing accepted inputs,
queues and historical requests retain their original method. Limits remain input
tokens; the lower model ceiling and output reservation still apply.

The first profile counts Unicode codepoints in the complete prepared request,
including instructions, tools, history, checkpoints and protocol fields. Its
fallback uses characters / 3 per disjoint component, plus 1,024 framing tokens and
16 per message, and separate raster reserves. Base64 image pixels are excluded
from text counting. This is a local planning estimate, not provider usage or a
guarantee about server-internal tokenization. Unknown media is not assumed free.

The same frozen profile feeds planning, summary/media helpers and the final
pre-dispatch check. Required input that cannot fit before any consumed history
exists reports its system, tools and conversation amounts. It is not described
as an unresolved tool observation. Transport byte limits remain separate.

Original request metadata keeps the request hash, Unicode characters, method,
version, model binding, reserves and disjoint categories. Historical schema-3
UTF-8-byte/raster estimates remain unchanged. Inspection does not execute inputs.

From 0.12.23 the default frozen profile uses pinned OpenAI tiktoken 0.14.0 for
exact upstream model mappings on the official OpenAI API or native Codex route.
The package and o200k_base/cl100k_base data are shipped with Studio, SHA-256
verified and loaded offline. The supplied binary targets CPython 3.13 on Linux
x86_64/glibc >=2.28. Unknown models, other connections and unsupported platforms
use the explicit character fallback. In particular gpt-6.1-sol has no entry in
the pinned upstream mapping and is not silently assigned another model's codec.

Text tokenization uses disjoint original JSON components; provider formatting,
tools and media make the complete result an estimate. It is not measured usage.
An encoding is loaded once per worker. The model/connection/credential revision
and content bind the text cache, limited to 32 entries of at most 256 KiB each;
larger texts bypass it. The final immutable request also reuses its full count.
Accepted character-only profiles from 0.12.22 remain character-only.

## Optional provider input counting (0.12.24)

The connection form offers **Use provider input token counting when needed**,
off by default. Only the documented official OpenAI Responses endpoint at
`https://api.openai.com/v1` with bearer authentication is qualified. Other
connections, including the native Codex subscription route, keep local counting
without discovery probes or another account. Saving only changes configuration
for future inputs; accepted runs retain their frozen choice.

When enabled, near-limit requests, unknown local mappings and media can use
`POST /responses/input_tokens`. The count projection preserves all supported
input-bearing fields while excluding stream/storage/output controls. An unknown
field is not silently dropped. A result is bound to the exact original body
hash, model, route, credential revision and policy. It can resolve a conservative
local rejection before compaction or dispatch. The lower limit still applies.

Count operations have their own `input-count` receipts and confirmed child ends;
they are not model turns, inference usage or dispatched LLM history. Replies are
limited to 64 KiB and the operation to eight seconds plus original-child cleanup.
Concurrent identical checks share one operation; up to eight results are reused
for 60 seconds. Failures back off for 30 seconds under the same binding and fall
back to the disclosed local method. Cancellation closes the original child.
No model retry, tool effect, account switch or automatic continuation follows.

The provider total is separate from local component estimates and later reported
model usage. Official contract: https://developers.openai.com/api/docs/guides/token-counting .
