# Z.AI GLM Coding Plan

0.9.39 adds a distinct subscription connection on the existing private API-key
store. Select **Z.AI · GLM Coding Plan** and enter your own plan API key. Keys
remain write-only; the normal revision, lease, original-request, rotation and
confirmed disconnect/delete contracts apply.

This product uses only `https://api.z.ai/api/coding/paas/v4` with Chat
Completions and Bearer auth. General prepaid API endpoints, other regions,
other protocols and local server presets are rejected. No paid fallback or
extra-usage option is enabled. Actual account rights are not established by
saving a connection. Model inference becomes available with the later GLM
transport integration; this release only delivers connection management.

The browser handles connection forms. The host owns keys and all transport.
Existing providers, sessions, model histories and SDK bindings are preserved.

0.9.40 adds the explicitly authorized OpenCode identity, frozen per original
session. A fresh upstream check found stable **v1.19.5**, commit
`810c0eba1a7348036f8bdf61e6632d0c36c6876c`. Its non-OpenCode-provider branch
sends `User-Agent: opencode/1.19.5`, `x-opencode-session-id`, `x-session-affinity`
and `X-Session-Id`. It does not send `x-opencode-client` or project attribution
for Z.AI. This stable original supersedes the development checkout's different
four-part User-Agent described in planning. Own opaque session aliases remain
stable across workers; no foreign identity or host path is copied. Only Z.AI
model requests get these headers. The monitor uses its separate native auth
contract, and internal native engine/provenance records remain unchanged.

0.9.41 adds GLM Chat translation and the existing native project/skill/Goal
runtime. Documented GLM-5.3 and GLM-5.3-Flash defaults use conservative decimal
1M context / 128K output limits, mandatory thinking and low/high/max effort;
omission retains the provider default. These are documented defaults, not an
account entitlement check or an allowlist: exact additional models can still
be saved with explicit facts. Metadata refresh preserves the documentation
provenance. Flash image input uses the existing original attachment/capture
bindings and bounded embedded images; it does not enable hosted MCP extras.

Thinking is preserved privately in `Codex/ZaiReasoning`, as exact originals
with hash-bound opaque native references. Tool rounds, worker restart and
native compaction reuse the same thread and original call ledger. Existing
OpenRouter records and their original reference format remain unchanged.
Native-only tier/cache/store hints and unsupported strict-provider hints stay
local; the host still validates every tool argument and permission. The Z.AI
tool-stream opt-in follows the documented GLM family contract.

0.9.42 adds original subscription monitoring through the host. The fixed
`/api/monitor/usage/quota/limit` GET uses the native raw `Authorization` token
documented by the official Z.AI plugin, separate from model Bearer auth. No
browser or tool receives either credential. Original requests, helper PID/birth,
credential leases and confirmed shutdown use the existing metadata lifecycle.
Rotation/disconnect retains unconfirmed original transports.

Limits keep their native credit/token/request units and independent windows.
Unknown values and absent resets remain unknown; cache failures retain stale
observations and do not establish an inference failure. Exact key rotation
invalidates the previous projection. Connections with the identical private
credential share an opaque scope; different keys are never merged merely by
name or plan tier. Z.AI still enforces account-wide limits across other tools.
Native quota originals stay private and never change numeric Run/Lifetime usage.
