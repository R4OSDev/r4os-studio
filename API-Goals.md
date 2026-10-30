# GOAL for API providers (0.8.60)

Compatible API sessions now use the pinned native Codex GOAL lifecycle for
Save, Play, live activation, Pause, Stop and status readback. This works over
the existing Responses and Chat Completions function transports. Studio supplies
the lifecycle; it does not require a provider-hosted Goal endpoint. Models still
need confirmed text, function tools, streaming and reasoning/default-effort facts.
Unknown model facts do not become supported because an endpoint is reachable.

Save and paused controls use an isolated metadata process with the original
native state, model catalog and stable API provider ID. Its network namespace
has no model transport; a fixed unreachable loopback endpoint replaces the
actual API endpoint. It claims no API credential or inference lease, creates no
relay and never resumes a thread or sets a Goal active. Status readback also
uses a separate process without credentials, networking, resume or a new turn.
Pause and readback retain this path after the API connection is disconnected.

Only explicit Play authorizes Goal execution. Idle Play admits its inference
worker and original API lease; live Play targets the existing worker.
`apiGoalProtocol:1` is frozen before lease reservation, alongside the original
Play, provider/credential revisions, model, effort, permissions and context.
An incompatible original snapshot cannot acquire Goal execution. Older queued
and running API snapshots are not upgraded or rewritten. The coordinator's
`apiNativeGoals:1` capability gates the browser controls; an older coordinator
keeps them unavailable until it adopts the matching implementation.

Live Save/Play targets the original Run/thread/turn and worker. The separate
activation record preserves the original API configuration hash and lease;
it does not insert a Goal into the frozen ordinary Run. The existing native
Goal controller retains queue priority, explicit Pause/Stop, original tool
receipts and passive recovery. Reading or restoring a session does not Play.
The selected reasoning effort is fixed at thread creation as well as resume,
so automatic Goal turns do not silently inherit another default.

Goal time uses the original Play clock. API spending statistics continue to use
explicit wire receipts and their original response identities, independently
of the native Goal's own accounting. Missing usage remains unknown; existing
transport, output and observation bounds apply. The relay remains drained after
the256-observation limit, retaining its confirmed prefix and marking later
coverage incomplete. Unsupported image input, hosted
web/image generation and Fast Mode remain unavailable through these adapters.

Verification uses owned isolated protocol receivers and the unchanged native
Codex0.163.0 binary: cold project/Responses and skill/Chat Save-to-Play paths,
same native thread, exactly one original file effect, completed Goal/clock and
released lease; disconnected Pause/readback and refused Play without a new Run.
Live activation additionally preserves the original ordinary Run/configuration
and lease. A selected-high-effort case checks every outgoing model request;
64 explicit wire tokens survive readback without duplication. Eight focused
Python checks and actual SessionPanel project/skill views at1440/320 cover
compatibility, original receipt recovery and Play/Pause/Stop controls.
These receivers are not real provider/model inference or new guest validation.

Roadmap0.8.17 remains open for the remaining shared retry and overall acceptance.
Active GOAL retry recovery is not enabled by this feature. No new provider-retry
tests or inference were performed under0.8.10's outstanding restriction.
See [Provider-Retries.md](Provider-Retries.md) and
[API-Session-Lifecycle.md](API-Session-Lifecycle.md).
