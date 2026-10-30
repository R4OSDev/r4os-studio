# Claude queued messages (0.8.47, partial lifecycle)

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
They are not real subscription/entitlement/billing evidence. Public Claude model
admission remains gated. Bounded GOAL controls/queue priority are added in0.8.49,
final stream statistics in0.8.50. Live activation, direct steering/retry and real
account acceptance stay open in0.8.19/21–23.
Existing Codex/API queues, native profiles and user data are preserved.
