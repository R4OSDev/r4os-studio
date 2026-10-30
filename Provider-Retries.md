# Provider continuations (0.8.10, supplemented in0.8.45)

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
