# Provider continuations (0.8.61, extended in0.8.68)

New compatible project and skill runs can recover from qualified temporary
provider failures in their original worker. This completes the ordinary-answer,
GOAL and Live-Goal integration for the pinned Codex/API and Claude runtimes.
The controller waits **60 seconds** after a confirmed failure and allows at
most **five additional attempts** without actual model progress. Authentication,
quota, policy, exhausted budgets and uncertain effects never qualify.

## Capture and compatibility

`retry_protocol.py` freezes numeric `goalRetryProtocol: 1` for the qualified
Codex0.163.0 runtime and private zero-retry provider or API adapter. It freezes
`claudeRetryProtocol: 1` only for the qualified Claude subscription session profile,
CLI2.1.312 and Agent SDK0.3.312 pins. Capabilities are captured before any API or
subscription credential lease is reserved. A protocol flag alone cannot authorize
inference; the living controller still checks every original receipt and gate.

Since0.8.68, compatible new Codex/API captures also freeze `streamRetryProtocol: 1`.
It enables only the exact observed response-body decoding failure described below.
Saved queues missing this flag retain its absence; existing running workers and
previously failed runs are not upgraded or restarted.

Previously saved runs and queues are never upgraded. A stored queue without a
flag keeps its absence and byte-identical configuration, including its existing
API lease hash. Unsupported saved values or incompatible runtime bindings hold
the queue before admission. No migration, timer restoration or automatic Play
follows from an update. Already running workers keep their immutable release.

## Shared admission and controls

The per-Run `provider_retries` ledger retains owner, session, original request and
input/config hashes, worker/native process identities and births, host boot,
release, native thread/session, confirmed tool receipts and original Play.
Each submission is claimed before native input. Fresh native account/API lease
or Claude subscription admission is checked again, along with current settings,
permissions, project pins, pending input, Goal controls and budgets. No new
worker or replacement thread can take over the timer.

Stop, Pause and queued user input take priority. The shared English session UI
shows a sanitized provider error, attempt/countdown, exhausted state or unknown
outcome. Pause remains reachable when a native Goal is temporarily Blocked during
retry waiting, including a Goal activated inside an ordinary response. Closing
that held Goal requires its original confirmed Play and current Run/turn binding;
it cannot authorize another Play or change its text. Run Stop remains accessible.

Model text or a confirmed native tool request resets the failure sequence.
Heartbeats and retry metadata do not. Waiting is excluded from the same monotone
Play clock and Claude active-time budget, and from project-folder activity.
Original usage and coverage gaps remain intact. Exhaustion holds the concrete
failure until an explicit human Send/Play starts a new request. Reload, multiple
tabs, coordinator recovery and host restart never restore an inference timer.

## Codex and API

Typed final HTTP502/503/504 `httpConnectionFailed` failures qualify. Since0.8.68,
the new stream capability also accepts a final pinned-native `other` error whose
message is exactly `stream disconnected before completion: Transport error:
network error: error decoding response body`. It needs no fabricated HTTP status;
the public retry contract reports `httpStatusCode: null` and a fixed safe message.
Arbitrary `other` errors, other stream failures, internal retries, unresolved
images/tools and unknown outcomes remain excluded. Ordinary responses use
`turn/start` with `input: []` in the same original process/thread, without a user
message ID or repeated prompt. Already completed tool results remain in that
thread; the controller does not resubmit the original prompt or tool calls.

A Goal additionally needs its confirmed original Play/Live-Play, unchanged human
control sequence, original active-to-blocked notification and complete current
failed native rollout section. The exact pinned binary logs function calls before
execution. Header/owner/file/EOF/context/model/ordinal/call-result checks exclude
model-issued Goal writes, incomplete effects and later activity.
A public Blocked notification or nearby503 is insufficient. Before submission,
the same original section and idle blocked Goal are read and checked again.

For the new decoding-failure path, a completed remote context checkpoint may
occur inside the fully retained original failed turn. Its exact known structure
must contain only historical messages and encrypted compaction, name the same
started turn, and have no outstanding calls at the checkpoint. The scanner still
checks every original call/result and ordinal before and after it. A checkpoint
never substitutes for missing originals, supplies a tool receipt or authorizes a
Goal write. Other checkpoint shapes and the older HTTP retry path retain their
existing hold. This uses the pinned native compaction installation and wire
definitions at `83086188ae0614bd882818ff1aa23f3194962012`.

Goal continuation uses status-only `thread/goal/set(active, origin: automatic)`
with no new objective, budget, user text or tool output. A matching new native
turn receipt is mandatory, including when it precedes the RPC response. The same
Play-clock row resumes. Lost or contradictory start evidence remains Unknown;
no speculative resubmission follows. Observational clock failure cannot grant
execution.

Native Codex0.163.0 is unchanged at SHA256
`399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`.
Its corresponding primary source is commit
`83086188ae0614bd882818ff1aa23f3194962012`. The private OpenAI provider keeps
HTTP/stream retries at zero, also when image generation is off. Old built-in
provider threads retain their original retry behavior and are not switched to
obtain another policy. API adapters preserve their original provider/credential
revision, native thread and lease; no key rotation or alternate provider fallback
is introduced.

## Claude subscription

The controller holds the original living SDK query after a typed final
502/503/504 structural boundary. It binds the native failure/input, model/runtime,
credential lease, history, Play/contract, logical step, confirmed tool receipts
and current controls. Claims and final admission use an immediate SQLite writer
transaction. Large tool results are not rehashed at heartbeat frequency.
Append-only `claudeRetryReceipt` events retain attempt metadata without raw
errors, prompts, headers, credentials or technical chat notices.

Each physical attempt requires fresh first-party account/model/usage admission,
with extra usage disabled. The same persistent query receives an empty block
array with explicit `auto-continuation` origin. It receives no original prompt,
upload, old tool output, string placeholder, fork or truncating resume. The
native UUID/session/logical-step echo must match the committed claim; the host
confirms it before tools reopen. Native hooks wait boundedly for both that
confirmation and the actual fixed model frame. The echo alone cannot establish
model identity. Live-Goal preparation additionally waits for broker confirmation.

Physical inputs remain inside the same logical Goal step. The accepted Play,
report, budget and prior receipts survive; `GoalClock.resume` reuses the same
execution. The separate Python ledger and native monotone guard exclude held
retry waiting. They cannot create more execution authority. Later refusals retain
the actual predecessor input ID and original result.

Pause/Stop cancels waiting, including during fresh admission. An already failed
idle input closes without interrupting a completed input. Exact original closure,
claim and readable history may prove that no new input was submitted. Otherwise
lost echoes, transport/result loss or conflicting receipts retain Unknown and the
clock's known prefix. A result from the previous failed input can never close an
acknowledged continuation. Storage/audit failure ends the worker and cancels its
resubmission task. Recovery observes records only; it never recreates a query.

### Pinned stream behavior

CLI2.1.312 / Agent SDK0.3.312 export internal `abandonedBlocks` as SDK wire field
`abandoned_blocks`. A synthetic `message_stop` alone proves no completion.
Abandoned frames, unpaired tools, compaction/internal-retry notices, missing
terminal deltas and conflicting identities exclude structural retry holds.
Incomplete endings retain usage coverage gaps instead of fabricated totals.

A terminal error may provide numeric `api_error_status` and finite `api_error`
kind. Only safe typed facts are projected; raw messages, headers, URLs and codes
are not rendered. Auth/quota/policy/context/model refusals win. Public
`system/api_retry` has no per-input UUID and is diagnostic only.

The native general retry budget remains zero. A separate dispatch-header
fallback can resend once per failing native request chain after503. The native
exhaustion proof observed six such resends for the original failure plus five
Studio continuations. These are bounded and counted separately; no native
backoff setting is substituted for Studio's fixed60-second delay.

An empty string becomes `(no content)` and cannot serve this protocol. An empty
array remains empty during model-message normalization. `isSynthetic` would
create a metadata row, suppress the native echo and change the context, so it is
omitted. The actual pinned runtime confirmed an identical retained model-message
wire and tool result, one original effect and one query/Run across continuation.

## Verification and practical limits

The0.8.68 extension was reviewed against the unchanged original R4Craft/Session II
failure and the pinned source. Its final turn contains838 contiguous records,
139 paired function calls/results and one completed remote compaction checkpoint.
Python syntax/AST, Build/TypeScript/Lint and installed-source checks cover this
change. **No tests, fixtures, native model calls or failure simulations were run
for0.8.68, at the user's explicit request.** The checks below describe the earlier
0.8.61 qualification and do not claim runtime coverage of the extension.

Targeted checks use the unmodified pinned native runtimes with owned synthetic
accounts and endpoints in closed network namespaces. They exercise successful
ordinary/Goal continuations, Live-Play, five actual60-second waits, progress reset,
Pause/Stop/Queue priority, exhausted quota, lost echo/transport/final result,
permission/lease changes, model-issued blocks and passive repeated recovery.
Capture/queue admission checks cover all three provider engines, old missing
flags, numeric1 and invalid values without changing reserved lease hashes.
Actual SessionPanel browser cases cover project/skill views at1440/320 pixels,
countdown/reload, bound Pause, Stop, exhaustion and Unknown.

Existing focused account/quota and active-time/recovery checks supplement these
cases. No broad suite or intentional real-account quota exhaustion is needed.
The earlier minimal authorized real Claude subscription proof remains the
account-integration evidence; these failure cases make no paid model calls.
A controlled queue-preemption case proves saved-byte retention, while earlier
qualified lifecycle cases cover subsequent dispatch. An unconfirmed effect,
unsupported protocol, unavailable provider capability or lost original worker
continues to hold rather than replay. Native R4OS desktop-retention/window
limitations remain separate roadmap dependencies.
