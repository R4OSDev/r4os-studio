# Claude after-response messages and queues (0.8.58)

While a compatible Claude response runs, **After response** and Ctrl+Enter store
an explicitly waiting follow-up bound to that exact run and native session.
The message appears as **After response** in the queue. Enter still uses ordinary
FIFO queueing. Attachments retain the existing frozen input contract. This does
not claim simultaneous native steering or put Claude IDs in Codex fields.

The new optional `afterRun` target is captured with the original intent before
POST and retained in its receipt/frozen queue selection. The host checks its
original worker/release; the message service requires the original live
configuration, provider/account lease and native session. An ended/changed
response cannot redirect a fresh intent to a later run. Reading an already
accepted request still returns its original receipt after that target ends.

Dispatch checks the exact saved input, target, source configuration/worker and
readable native history. Natural completion can release the original authorized
queue. After a confirmed failed/interrupted source, a new explicit Continue
queue command must follow the source end. Its original body/hash, receipt,
frozen input hash and creation time remain in a private resume record. Retrying
an earlier Continue cannot create later authority. Unknown, changed bindings,
unreadable history and current admission/permission failures remain protected.
No read, reload, reset clock or coordinator restart resumes the queue.

An explicit Claude Goal Pause now holds queued follow-ups; Continue remains a
separate human action. A Goal yielding to an already authorized queue at its
step boundary leaves that queue eligible. Stop closes admission and holds it.
The saved message/attachments can still be cancelled without losing receipts.

Seven focused new Python cases cover source/target/intent identity, FIFO,
original message and native IDs, later human Continue, forged/stale control,
Unknown, Stop, Pause, cancellation and restart holds. Four existing cases cover
ordinary Claude queue priority/lease checks and Codex FIFO/direct compatibility.
An unchanged SDK0.3.312/CLI2.1.312 case used the production worker, namespace,
admission, message store and host queue dispatch in an owned closed TLS/account
namespace. A launch callback replaces systemd in that fixture. Two actual native
runs shared the original session UUID: the follow-up waited for natural source
completion, retained its distinct input receipt and resumed readable history.
One original tool effect remained one, with the original tool receipt present
in the resumed model context. Its file effect used an owned callback behind the
common receipt broker; this is not a new qualification of the file sandbox.
No actual connected-user subscription inference was used for this release.

The actual Project/Skill SessionPanel, composer and inbox were checked at1440
and320px with owned API/event responses: native Ctrl+Enter, exact waiting target,
lost response, read-only reload with one original POST, Stop and explicit
Continue. Reduced Motion was enabled at320px. A corrected flex parent in the
mobile fixture also confirms the waiting button is visible without scrolling;
no product CSS change was needed. These UI responses do not constitute a public
backend inference test. The actual Pro text/input/live Goal evidence remains
in52/55/57. Automatic retry integration and full lifecycle acceptance remain
open in0.8.23; no retry fixture or retry inference was added here.

## Existing queued input contract

Since0.8.55 queues also freeze explicit document/image blocks and their ordered
content digest. The native stdin echo must confirm that content before any
Studio effect. Later response frames reuse that original receipt without
requiring a second content echo. The unchanged SDK/CLI, production admission and
common file broker were checked with an owned queued image/document/skill case.
See [Claude-Inputs.md](Claude-Inputs.md). Direct steering and the remaining23
overall lifecycle acceptance stay separate.

Compatible Claude sessions can accept text follow-ups into the existing shared
message queue while their original worker is active. Saving an intent starts no
model. FIFO dispatch waits for the preceding run to end and for the original
native history to be ready. Each new native process resumes the same session
UUID and performs fresh account, model, quota and overage admission.

The frozen queue selection binds the native session/runtime, provider revision
and account identity. Capture during an opening/active history additionally
requires the original live worker PID/birth/release, configuration and current
credential lease. It does not scan or freeze a changing native transcript.
After completion, dispatch checks the original source run and the unchanged
selection. Account/settings changes, unreadable history and unknown outcomes
hold the input instead of sending it to another target. Queue recovery after a
coordinator restart still requires explicit Continue. Cancellation retains its
receipt and text; a queued intent acquires no unused credential lease.

## Native input acceptance

The local `submitted` event means only that input was handed to the native
transport. It cannot accept a queued message. The adapter enables the fixed
`--replay-user-messages` flag for queued runs. This emits a native stdin
acknowledgement on stdout; it does not submit another prompt. Reference:
[Claude CLI](https://code.claude.com/docs/en/cli-reference).

An input echo must match the original UUID, native session and exact UTF-8 text
hash. Supported response input-ID stamps may also confirm receipt. Initialization
and status tags never constitute acceptance. The private Node projection removes
echoed text, so it cannot duplicate the user's transcript entry. Studio stores
the original input binding and native receipt atomically with the Accepted
message state; no native turn ID is invented. Duplicate confirmations retain the
first receipt. A missing/conflicting receipt holds an unknown original request
without resubmission or history repair.

Queued tools require receipt confirmation in both the native adapter and host.
A bounded host wait accommodates stdout/socket delivery order. A denied call
receives an immutable no-effect receipt; later confirmation cannot execute that
same call ID. Stop closes effect admission while retaining a positive input
receipt that was already observed. Failure/Stop/Unknown keep later messages held.
Direct Claude steering and automatic retry remain unavailable pending their
separate qualification; use the visibly bound queue for follow-ups.

## Qualification and remaining work

Twelve focused Python cases and nine Node cases cover queue capture, duplicate
requests, FIFO, missing/foreign input receipts, metadata tags, Stop, immutable
denial, account revision changes, cancellation and restart holds. An owned
network/filesystem-isolated case ran the actual unchanged SDK0.3.312 and
CLI2.1.312 through two worker paths, queued during the first active run, and
dispatched once after natural completion on the same native UUID. Two separate
admission calls preceded input; one original tool effect remained one after a
replayed tool ID. The native input echo and both closed streams were confirmed.

These controlled cases use synthetic auth and an owned fake Messages endpoint.
They are not real subscription/entitlement/billing evidence. At the original0.8.47 checkpoint, public Claude model
admission was still gated;0.8.52 qualified the native text selection. Bounded GOAL controls/queue priority are added in0.8.49,
final stream statistics in0.8.50. Live activation and real input acceptance were subsequently qualified in52/55/57.
Explicit bound waiting is added above; actual simultaneous steering is not
claimed, and retry/full lifecycle acceptance remain open in23.
Existing Codex/API queues, native profiles and user data are preserved.
