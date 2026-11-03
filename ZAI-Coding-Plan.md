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
