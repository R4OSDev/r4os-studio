# Z.AI GLM Coding Plan

0.9.39 adds a distinct subscription connection on the existing private API-key
store. Select **Z.AI · GLM Coding Plan** and enter your own plan API key. Keys
remain write-only; the normal revision, lease, original-request, rotation and
confirmed disconnect/delete contracts apply.

This product uses only `https://api.z.ai/api/coding/paas/v4` with Chat
Completions and Bearer auth. General prepaid API endpoints, other regions,
other protocols and local server presets are rejected. No paid fallback or
extra-usage option is enabled. Actual account rights are not established by
saving a connection. Model inference is available through the native GLM
transport added in 0.9.41.

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
# Shared subscription limits (0.9.43)

Only a successful native quota observation or an original model error can hold
the associated subscription scope. Identical private keys share an opaque scope;
different keys are not merged from account names or plan labels. A model-access
error holds that selected model. Weekly exhaustion remains independent of a
free 5-hour allowance. Missing monitoring or reset data never means zero usage
or a new estimated reset.

Admission and credential claim both check confirmed holds. A hold observed
during a run blocks subsequent model calls while preserving the original
in-flight response, confirmed tool receipts, Goal and queue contracts. A native
reset or a fresh successful positive quota check can permit another explicit
attempt; neither starts or resumes work. Native 1302/1305 overload/rate errors
remain separate from 1308/1310 exhaustion, expired plans and model restrictions.
The existing retry policy remains authoritative; no provider/model fallback or
paid extra usage is enabled.

The global endpoint publishes both address families. Z.AI selects a validated
IPv4 address first on dual-stack DNS, before opening credential transport. The
full DNS answer still passes the network-scope check; TLS retains api.z.ai,
and one admitted request still makes exactly one HTTP attempt.

## Subscription display (0.9.44)

Provider settings and Z.AI project/skill sessions display the same private
account observation: plan, distinct native windows, units, used/remaining/maximum,
observation time and only reported resets. Reported, stale, unknown and confirmed
holds are distinct. Credit allowances never become session token estimates.
Refresh is explicit; visible views reread the local projection every 15 seconds.
Original refresh IDs/revisions survive reload without keys or request replay.
During a running original request, a later credential change cannot substitute
the new account's limits for its frozen scope. Original receipts remain readable.
The session's normal statistics continue to report actual run usage separately.

## Real subscription qualification (0.9.45)

The implementation is exercised with a user-connected Coding Plan through the
normal private credential lease and current native Studio engine. Real GLM-5.3
tool rounds, original file updates/readbacks, thread continuation, a small native
Goal and original account limits are distinct from the isolated TLS fixtures.

An observed provider response encoded a new file's `expectedSha256` as the
string `"null"`, although the original schema allows JSON null. Studio preserves
and checks the actual arguments. It never coerces that string into permission
to write. When both file tools are offered, a short model guide recommends the
existing Add File patch operation for new files and the actual read SHA256 for
existing-file replacements. Schemas, arguments, rights and original receipts
remain unchanged. Unsuccessful provider operations stay visible in history.

The qualification does not exhaust real quota or test paid extra usage. Credit
snapshots may include account use outside Studio; no delta is attributed solely
to these runs without its original evidence. Existing user projects, sessions,
providers, SDK defaults and VM identities are preserved. Only owned temporary
qualification resources are removed after their original work has ended.
