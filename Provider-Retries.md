# Provider continuations (0.8.10, supplemented in0.8.45)

## Unreleased controller candidates

The current source adds original-worker Codex/API GOAL recovery and native
Claude subscription retry controllers. These paths are **disabled and not
runtime-qualified**. Active Codex/API GOAL recovery requires a frozen numeric
`goalRetryProtocol: 1`; Claude requires `claudeRetryProtocol: 1`. No capture
producer currently sets either field. Existing runs/queues are not upgraded.
Released ordinary Codex/API retries and normal GOAL execution remain available.
No0.8.61 release/tag/installation is authorized by static checks alone. The
separate requested exception for targeted retry tests is still unanswered;
no new runtime fixture, SDK/CLI execution or inference was performed.

### Codex/API GOAL candidate

The shared60-second/five-attempt controller additionally binds the confirmed
original Play or Live-Play, unchanged human control sequence, original native
active-to-blocked notification and complete **current** failed rollout section.
Pinned0.163.0 logs function calls before execution. Strict header/owner/file/EOF,
context/model/ordinal/final HTTP and call/result checks exclude Goal writes,
unknown calls, incomplete effects, compaction, replacement and later activity.
The same original file/section proof is checked again before claiming submission;
a public blocked notification or empty scan cannot authorize reactivation.

Status-only `thread/goal/set(active, origin: automatic)` supplies no new user
text, objective or budget. A matching new native turn receipt is mandatory,
including when it precedes the mutation response. Missing or contradictory
submission remains unknown and is never submitted again. Pause/Stop cancels the
original timer; the evaluator holds that original worker throughout waiting and
rechecks its gate after asynchronous readback. The same monotone Play-clock row
resumes without waiting-time accrual. Clock failure marks a coverage gap and
cannot grant execution. Historical503 prefixes prove shape only, not live
admission. The additional frozen protocol gate stays off until qualification.

### Claude original-query controller candidate

The controller binds owner/session/Run, original request/configuration, worker
and wrapper PID/birth/release/boot, exact native session/runtime, credential
lease/account, current history, settings and project pins. All Studio tool
results must be confirmed and unchanged. Original Play/contract digests and the
logical step are retained separately from each physical input UUID. The existing
`provider_retries` row stores the current counter, deadline, claim, admission and
receipt; append-only `claudeRetryReceipt` events retain the attempt audit without
technical chat notices or prompt/credential content. Browser/host recovery only
observes these records; a replacement worker cannot restore their timer.

A qualified typed final502/503/504 structural boundary can hold only the living
original SDK query and suspend tools. The Node proof is explicitly
runtime-unqualified; the disabled frozen protocol is not inferred from a status
number or absent response. The original native failure/input, complete tool
receipt hash, controls and limits are checked before60-second waiting, before
claiming and after fresh subscription admission. Claims and the final admission
are committed under an immediate SQLite writer transaction. Goal controls are
also serialized with the original control lock. Waiting polls metadata only;
large tool results are not hashed repeatedly at heartbeat frequency.

Every physical attempt needs a fresh first-party account/model/usage admission
with extra usage disabled and its exact claim returned to Node. It supplies an
empty block array in the same persistent query, not a repeated prompt, upload,
old tool output, string placeholder, fork or truncating resume. The exact native
empty-array echo must match the claimed UUID/session/Run/logical step. The host
confirms its committed receipt before either broker or SDK hooks reopen tools.
Submission/status/metadata alone never confirms input. At most five attempts
are allowed without actual model text/tool progress; status events do not reset
that count. The original human/logical-step receipt remains confirmed throughout.

Goal physical-attempt pointers, admissions and echoes stay inside the same
logical step, with earlier attempt receipts retained in the audit. The original
accepted Play, report, bounds and successful tool receipts are not replaced.
`GoalClock.resume` reuses the same execution row after the new echo. The separate
Python authoritative time ledger and Node monotone guard exclude retry waiting;
statistics cannot grant more execution. A successful physical result records its
actual input ID, so later refused Goal inputs still retain the correct predecessor.
For live activation during an ordinary recovered response, the target additionally
binds its committed physical echo and claim digest. Root Run/request identity stays
unchanged. Native arm, source result and later no-input closure must all identify
that actual source input; waiting or unconfirmed retry admission cannot arm a Goal.
Legacy targets without this private protocol retain the original source identity.

Pause/Stop cancels the timer, including during fresh admission. An idle failed
query closes without interrupting an already completed input. Claimed but
unconfirmed starts are held, not repeated. A matching final closure can prove
no new input only with the exact claim, original source result/input, readable
history and confirmed stream closure. Other missing/foreign/conflicting receipts
retain Unknown and the clock's known prefix. Storage/audit failure still ends
the worker and cannot leave a model-resubmission task running. Quota/auth/policy,
complete/blocked reports, human controls, queues and unknown tools win. Folder
activity excludes waiting and submission admission; stopping stays visible until
its original process ends.

### Pinned Claude stream and error facts

The unchanged runtime is Claude Code2.1.312 / Agent SDK0.3.312. The CLI exports
internal `abandonedBlocks` as the undeclared SDK wire field `abandoned_blocks`;
the SDK passes through that original record. A synthetic `message_stop` alone
cannot prove completion. Missing terminal deltas, abandoned frames, unpaired
tools, compaction/internal-retry notices and contradictory identities exclude
structural holds. Incomplete response endings publish no completed input/output
usage counters and retain a coverage gap. Historical totals are not repaired.

Terminal `success`/`is_error: true` can expose a numeric `api_error_status` and
finite `api_error` kind. Projection preserves only typed safe facts and the
presence of a server code, never raw errors, headers, URLs or the code itself.
Auth/quota/policy/context/model refusals take priority. Missing HTTP status
cannot authorize retry, while known safe server/overload descriptions remain.
Public `system/api_retry` has no per-input UUID and remains unqualified diagnostic
information. Absence of that event does not prove no internal resend.

General retry/watchdog/nonstreaming/model-fallback settings stay unchanged.
In particular, a separate one-time first-party dispatch-header fallback can
resubmit after503 even with the general retry budget at zero. It must be
accounted for separately. General jitter/backoff or overloaded-only delay knobs
are not substituted for the shared fixed60-second/five-attempt contract.

The exact empty string passes the whitespace guard but becomes `(no content)`.
An empty array instead remains empty and is skipped by model-message
normalization, as are synthetic API-error rows. This is source evidence, not an
actual retained-query/model-wire/tool-preservation qualification. The private
transport refuses a changed echo instead of replaying original input.

### Still required before enabling

Actual retained-query continuation, wire/context equality, counters/exhaustion,
Pause/Stop/Queue races, original Play/statistical clocks, admission/result loss,
restore, ordinary-response Live-Play after a physical retry and shared-account
cases remain unqualified. Both frozen
protocol producers remain off. The full0.8.10/17/23 acceptances stay open;
static checks and source inspection do not complete them.

## Released ordinary-answer controller

New compatible project/skill workers can continue ordinary answers after a
confirmed final HTTP502/503/504 `httpConnectionFailed` turn. They wait60seconds
and admit at most five additional attempts per failure sequence. A continuation
uses the original native process/thread and `turn/start` with `input: []`, no
user-message ID, tool output or repeated prompt. Model text or a native tool
request confirms progress; only that progress resets the failure sequence.

The durable per-Run ledger freezes owner, session, original request/input/config
hashes, worker/native PID and birth, host boot, release, thread, failed turn and
all confirmed tool receipts. It records the counter and monotone deadline before
waiting, then claims each submission before RPC. Browser reloads and coordinator
reconnects can observe this ledger; they cannot create a timer or start inference.
Worker/host loss never resumes it. A lost start without an original native
receipt becomes unknown; it is not submitted again.

Before each attempt, the worker serializes with direct-message and Goal-control
locks, checks the exact frozen session/config/engine, project pins, original
processes, current account or API lease, native idle state and unchanged tool
receipts. Stop, queued/pending/unknown input, pending Goal controls, changed
rights/bindings, unresolved images/tools, native internal retries and partial
stream errors exclude continuation. Tool admission is closed while waiting or
claiming a continuation. Repeated old turn boundaries cannot end the new turn.
The pinned native `systemError` status is also idle when no turn or input request
is running; the exact qualified final HTTP failure remains mandatory.

Project/skill views share a safe error, attempt and monotone countdown display.
Stop remains available, direct send is unavailable at the idle retry boundary,
and retry waiting does not animate the project folder as execution. No native
usage or cumulative token event is converted into a new spending receipt.

The supplement also fixes API context admission: `contextProtocol` is frozen
before reserving the API lease. A worker does not append this field to an older
API snapshot after reservation. Its original hash remains intact; missing legacy
context coverage stays unknown. No historical lease, run or queue snapshot is
rewritten to make a changed configuration appear original.

### Pinned Codex GOAL boundary reviewed in0.8.59

The installed Codex0.163.0 source at
[`83086188ae0614bd882818ff1aa23f3194962012`](https://github.com/openai/codex/tree/83086188ae0614bd882818ff1aa23f3194962012)
confirms a final turn error can set an active Goal to Blocked before publishing
the terminal error. The public `thread/goal/updated` notification includes an
optional `turnId`, but omits the private event ID and specific transition cause.
A model-issued Goal update can carry the same turn ID. Turn correlation and a
nearby transport error therefore do not independently prove that only the
transport failure caused the block. A status-only `thread/goal/set` can preserve
usage but can also start work immediately; it does not supply that missing
cause or a conditional original-failure permit. No automatic reactivation was
added. Model/human blocks and Stop/Pause remain authoritative. This is a source
finding, not a provider-retry runtime qualification; no retry fixtures or
inference were added for0.8.10.

**Still open:** active GOAL/Live-Play recovery and its pause/clock/budget/queue
integration, plus positive integrated runtime acceptance. This controller does
not take over GOAL execution. Tasks2/3 remain partial and task4/acceptance remain
open. No new tests/browser fixtures, artificial retries, paid inference or user
session/VM actions were performed for this supplement. Source/import/AST checks,
Build/TypeScript/Lint and installation readback do not claim those runtime cases.

## Earlier diagnosis (0.8.10)

Implemented: safe typed provider error descriptions in project/skill workers,
including final failed-turn errors and native error notifications. The UI can
show `Model service unavailable (HTTP503).` instead of a generic provider error.
Only known enum names and valid numeric HTTP status codes are retained. Raw
provider messages, URLs, request identifiers and additional details are not
forwarded. The previous narrow authentication/quota fallback stays sanitized.
A transient candidate is a diagnostic classification, never retry permission.

The original0.8.10 release implemented diagnosis only. The ordinary-answer
controller described above is additive in0.8.45; existing workers retain their
original immutable release. Successful recovery has not been asserted from an
unobserved runtime case. The remaining roadmap items stay open.

## Qualified sources

The installed unmodified Codex0.163.0 binary is pinned at SHA256
`399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`.
Its source checkout is commit `83086188ae0614bd882818ff1aa23f3194962012`.
Relevant files under codex-rs:

- app-server-protocol/src/protocol/v2/shared.rs and notification.rs:
  typed connection errors with optional HTTP status, finality via willRetry.
- app-server-protocol/src/protocol/common.rs and v2/turn.rs:
  public turn/start/steer/interrupt methods and their inputs.
- app-server/src/request_processors/turn_processor.rs and
  core/src/session/turn_input.rs: an idle turn/start with empty input can start
  sampling without adding user content; it remains a new native turn. Active
  empty steering is rejected. There is no public original-attempt retry/CAS RPC.
- model-provider-info/src/lib.rs and core/src/responses_retry.rs:
  native retry counts,200ms HTTP base delay, stream backoff/server advice,
  transport fallback and cancellation. They do not expose the Studio contract's
  uniform60-second delay or durable per-Run attempt ledger.

Current official references describe the public
[app-server lifecycle](https://learn.chatgpt.com/docs/app-server) and configurable
[HTTP/stream retry counts](https://learn.chatgpt.com/docs/config-file/config-reference).
Current documentation is not substituted for the pinned binary's behavior.

Studio's private `studio_openai_images` provider deliberately keeps HTTP and
stream retries at zero, including when image generation is disabled. An image
POST with an unconfirmed outcome must not be replayed. Old built-in-provider
threads have different native retry behavior; provider identity is not changed
to obtain a different policy. No Codex source/binary/profile/pin was modified.

## Continuation contract to implement

1. Consider only a typed HTTP502/503/504 failure at the pre-response connection
   boundary and a confirmed final failed native turn. The0.8.45 controller uses
   only the HTTP connection class; stream connection classes stay diagnostic.
   Missing status, a partial
   or disconnected response stream and unknown request/tool effects do not prove
   safe continuation. Authentication, account/quota, context/budget/storage,
   policy blocks, complete/blocked Goals and human Stop/Pause are excluded.
2. Wait60seconds after each final failure and allow at most five additional
   attempts in one failure sequence. Only confirmed model progress resets the
   count. Native retries, transport fallback and Studio retries must not multiply.
3. Persist original owner/session/Run, worker PID/birth/release/host boot,
   thread/failed turn, frozen configuration, original Play and tool-receipt
   binding. Reconcile those exact records before each attempt. No replacement
   thread, new user text, replayed original prompt or replayed acknowledged tool.
4. A qualified idle continuation must preserve the existing context. Empty-input
   turn/start alone is not sufficient admission: the controller must serialize
   Stop/Pause/Queue, current thread state, Goal changes and the original receipts.
   A lost continuation response becomes unknown and is never submitted again.
5. Web/coordinator reconnect may observe a living original worker chain only.
   Worker/host loss never triggers new inference. Reconnect, tabs and settings
   cannot reset the counter or create a second timer/Run.
6. Retry waiting is waiting time. Exclude it from active Goal clock accrual and
   project-folder activity; preserve native usage, budgets and the original
   execution identity. Do not infer elapsed time or model progress from heartbeats.
7. The UI must show a safe concrete error, next attempt1/5–5/5 and remaining
   wait while keeping Stop reachable. Exhaustion holds the original failure;
   a later explicit Send/Play is a new human request.

## Remaining qualification

The idle continuation's actual request/result loss, tool receipt preservation,
native Goal pause/resume, clock and Queue/Stop races require an integrated
controller qualification. Source inspection does not prove those runtime cases.
Roadmap0.8.10 explicitly excludes new tests/browser fixtures/inference without a
later separate instruction. The original0.8.10 release added diagnosis and the
contract. The0.8.45 supplement implements the narrowly qualified ordinary-answer
path described above; it does not claim GOAL recovery or positive end-to-end
qualification. No tests, fixtures, inference or user session/VM actions were
performed.
