# Bounded Studio GOAL engine (0.8.48, private qualification)

The Claude worker has a separate Studio orchestration source. It sends no Codex
Goal RPC and does not treat a Claude `/goal` event or a successful response as
an equivalent control API. Public Claude Goal buttons and model admission
remain gated. The user-facing Save/Play/Pause/Stop adapter, live activation,
queue handoff and real subscription acceptance still need qualification in
0.8.23. This release qualifies the private execution engine underneath them.

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

The fixed `report_goal` facet exists only during this private bounded execution;
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

Synthetic auth and the owned Messages endpoint do not prove a real subscription,
entitlement, quota or invoice. Ordinary native queue and Stop/resume behavior
remain separately qualified. The public account/model and GOAL-control gates
are retained until the remaining integration and account evidence exist.
