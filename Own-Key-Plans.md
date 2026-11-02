# Short own-client key plans (0.9.7)

New `studio-tools-v21` conversations may send `kind=keyPlan`, a recent focused
own `frameId`, and1..32 `steps`. Each step supplies either a normal `key` or a
printable Unicode `codepoint`, plus `atMilliseconds`0..2000 in monotonic order.
The allowlist is the existing GUI-input-v2 navigation/printable key contract.
Control characters, surrogate codepoints, Ctrl shortcuts, physical holds,
clipboard operations and conditional branches are excluded. Ctrl+A remains a
separate immediate semantic shortcut. Original conversations retain their exact
declarations and behavior.

The host validates the entire plan before submission, checks the original own
run/input permission, process generation, window/frame, focus and geometry, and
requires a newly deployed helper reporting `keyPlanVersion=1` and frame binding1.
It persists the original action ID, normalized plan and frame before one native
submission. The original guest watchdog copies the bounded plan and uses its
monotonic clock to dispatch events without host/model roundtrips between steps.
It rechecks its exact owned process, relay, visible focused window and geometry
before every event. Stop, the original application deadline, transport loss,
binding change or its two-second plan bound abort the remaining suffix. Other
input cannot interleave with an active plan. No key or modifier remains held.

Original receipts report accepted/expected, active, actual enqueue-call times,
lateness and abortedReason. `timingObservation=monotonic-enqueue-call-start`
identifies what was measured; scheduled time is not actual dispatch or app
consumption. Intermediate/final receipts are saved privately and the job's
`lastKeyPlan` is visible in ordinary readback and the development card. A lost
response remains unknown; it is never replayed. Existing action deduplication
returns only the original completed receipt or protects an unconfirmed action.

For example, normal `R` then `ArrowRight` at100ms can be scheduled without a
second tool roundtrip. This does not prove that a game completed a search before
the second event. Observe a new own image/output afterward. Studio changes no
application clock, rules, inventory or state to manufacture a result.

No tests, fixtures, inference or user app/VM runs are executed for this release.
Static checks and both private helper builds use the existing private pins.
Positive native dispatch/abort acceptance remains open pending actual evidence.
