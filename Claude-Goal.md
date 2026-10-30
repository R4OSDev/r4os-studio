# Bounded Studio GOAL controls (0.8.49, partial qualification)

The private same-query transition from an ordinary response to a separately
authorized Goal is protocol-qualified in0.8.56; see
[Claude-Live-Goal.md](Claude-Live-Goal.md). It still needs public Save/Play,
durable live-ledger, recovery and UI integration. Actual Pro-account ordinary
text/tools/resume and image/document/skill checks have since passed in52/55;
the original statement below deferring all real account acceptance is historical.

The Claude worker has a separate Studio orchestration source. It sends no Codex
Goal RPC and does not treat a Claude `/goal` event or a successful response as
an equivalent control API. The shared Goal controls now have a provider-specific
Save/Play/Pause/Stop adapter in project and skill sessions. Public Claude model
admission remains gated. Activation inside an already running ordinary response
and real subscription acceptance remain open in0.8.23. The user explicitly
deferred the real account acceptance; no account connection is needed for these
owned protocol checks.

## Saved intent and controls

Save and readback only access the owning Studio session. They launch no native
process or account request. The saved source is `studio-claude`, with a separate
Goal ID and native Claude session UUID; Codex `threadId` and unknown `tokensUsed`
remain null. The UI exposes the eight-step/15-active-minute bounds and preserves
drafts while the original run is busy. Editing or starting another Goal waits
for that run to close. An existing pending message queue takes priority over
Play and must first be continued or removed.

Play uses the original accepted request and frozen selection. Its positive
native input receipt confirms activation. Pause reaches the original worker
through its private, UID-checked socket, revokes subsequent input admission and
waits for the current admitted step. Stop also closes tool admission immediately
and requests the native interrupt. The saved command, original worker
generation and configuration must still match. Repeated or disconnected
requests read their original receipt. A later explicit Stop cannot be undone
by a delayed Pause. The still-running original worker can drain an accepted
revocation after coordinator delivery is lost; recovery never resends model
input or creates new Play authority.

An authorized queued message takes priority after the current Goal step and
confirmed stream/history closure. The common queue then submits the saved
message on the same native conversation, with fresh admission and its own
native input receipt. It does not become another automatic Goal step. Stop,
unknown outcomes, changed bindings and held queues retain their existing
dispatch protections.

## Original authority and limits

An immutable contract must come from the original accepted Studio Play command
for the same native Claude session. It binds the saved objective and its hash,
command fingerprint, session revision, original request and execution IDs.
One Play permits at most eight steps and 900 active seconds. The original
worker, boot, PID/birth/release, frozen configuration and credential lease remain
bound. An existing execution ledger cannot be attached, restarted or reset.
Reading or recovering a lost ledger never launches a model.

Each step has a distinct native input UUID and text hash, fresh account/model/
subscription/overage admission, a positive native input receipt, a progress
report and a distinct native result. The first input is the original saved
objective activated by Play. Later inputs use a fixed continuation instruction,
`origin: { kind: 'auto-continuation' }` and the same native conversation. They
grant no new human authority or tool permissions. The pinned CLI omits that
non-human origin tag in its saved transcript; Studio therefore retains the
automatic provenance in its own protected step ledger. Missing native origin
is never relabeled as human. No native turn ID is invented.

The fixed `report_goal` facet exists only during this bounded execution;
existing Studio tool profile declarations stay unchanged. It records continue,
complete or blocked with a reason. Its immutable receipt does not itself start
work or prove that the objective is complete. Before continuing, the host also
requires the original native result, confirmed input and tool outcomes, a live
original worker, remaining bounds and a fresh admission. Duplicate reports
retain their first receipt and cannot report progress for a later step.
Denied reports cannot become successful after a delayed input acknowledgment.

Stop closes tool admission first. Unknown effects, possible partial changes,
missing input receipts, account holds or changed bindings prevent another step.
Automatic steps cannot release an account hold. A native error does not trigger
an automatic retry. Missing progress reports leave the Goal blocked. Completion
remains provisional until original native stream/history closure is confirmed;
an unconfirmed closure stays unknown. Monotonic time starts at the first
positive native input receipt and feeds the existing numeric Goal lifetime
outbox under the original execution ID.

## Qualification

Focused journal/transport cases cover original authority, duplicate execution,
native input/report/result evidence, immutable denials, Stop, unknown effects,
unconfirmed closure, passive recovery and the step/time caps. A controlled run
uses the actual unchanged SDK0.3.312 and CLI2.1.312 in owned filesystem/network
namespaces: two steps, two native input echoes, two fresh admission callbacks,
two native result IDs, one native conversation and one monotonic Play clock.
A repeated native file-tool ID retains exactly one original effect.

Additional controlled cases use actual Host Save/Play/Pause/Stop commands and
the unchanged pinned SDK/CLI. They confirm local Save without a model process,
native-confirmed Play, bound Pause, native Stop and a queued normal response
after Goal closure on the same UUID. Browser checks use the production hook and
components against an owned API fixture in both session scopes at1440/320px,
including reload, disabled controls and explicit bounds. They do not connect a
real account or exercise a user session.

Synthetic auth and the owned Messages endpoint do not prove a real subscription,
entitlement, quota or invoice. Public account/model admission stays gated.
Live activation, remaining direct/retry integration and overall real
subscription acceptance remain open rather than being inferred from these
isolated results. Final stream token accounting is qualified separately in
[Claude-Input-Usage.md](Claude-Input-Usage.md).
