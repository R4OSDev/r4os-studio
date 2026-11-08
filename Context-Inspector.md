# Context request inspection

## 0.12.18 — original capture

New direct Studio requests retain the exact final UTF-8 JSON body before the
HTTP child starts. This includes provider prefixes, tool schemas, cache markers,
materialized documents and inline media. Main requests, summaries, vision and
image generation share the same capture boundary. Transport credentials and
headers are outside this body and are not archived.

Private session storage keeps the SHA-256, length, model facts and frozen context
policy with each operation. Bodies use zlib compression and session-local content
addressing. The archive retains up to 96 MiB of compressed bodies and the latest
10,000 request records per session. Older bodies may expire while their identity
and hash remain; expiration is explicit. Session deletion removes the archive
and its byte accounting in the existing deletion transaction.

Capture failure prevents a new supported dispatch. A prepared body, a dispatch
attempt and a provider response are separate observations. A child process start
is not proof of provider receipt. Existing receipts, accepted worker versions and
uncertain original effects are preserved.

Legacy native Codex/Claude SDK adapters do not expose their final provider HTTP
body to Studio. Their existing aggregate context measurement is retained, but a
complete request cannot be invented from an SDK transcript. Older direct calls
without a retained body are likewise unavailable. No SDK change or automatic
conversation conversion is performed for inspection.

The history API and overlay follow in 0.12.19–21.

## 0.12.19 — context and history

Each new captured body also freezes a disjoint estimate for System prompt,
Tools, Conversation and Other / protocol. Estimates use original JSON spans,
including exact escaping, and the same conservative UTF-8/framing/raster basis
as input admission. Free and overflow use that basis and the frozen effective
input ceiling. The model window and reserved output/headroom are separate.
Legacy policies without full-input admission are labeled accordingly.

Provider-reported input and cache usage remain separate from estimated
components. Cache read/write counts contribute once; output is excluded. No
provider aggregate is arbitrarily distributed across categories. Unknown media
estimates remain unavailable, without preventing access to an intact body.

Authenticated project and skill session reads provide cursor-paged lightweight
metadata, a selected request with older/newer identities, and on-demand byte
ranges or complete download. Prepared-only calls are excluded. Original
0.12.18 bodies can be analyzed using their frozen facts and policy; current
settings are never substituted. All reads preserve stored original records.
