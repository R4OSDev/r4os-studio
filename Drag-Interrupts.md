# Bounded drag interruption checks

Studio0.8.83 adds an optional `interrupt` to `studio_send_vm_input` gestures in
new project sessions with tool profile17. The original down/move/up plan remains
bounded to32 steps and2000 milliseconds, with its final button release in the
same call. Existing native conversations keep their exact declarations; profiles
1–16 do not gain undeclared fields. A new deployment provides the separately
qualified `dragInterruptVersion=1` helper. The app artifact and project pins do
not need to change just to deploy the new adapter.

An interrupt runs after the last held step and before the final `up`:

```json
{
  "jobId": "<own-execution-id>",
  "kind": "gesture",
  "frameId": "<recent-own-focused-frame-id>",
  "steps": [
    {"phase":"down","button":"left","x":100,"y":120,"atMilliseconds":0},
    {"phase":"move","x":180,"y":150,"atMilliseconds":150},
    {"phase":"up","button":"left","x":180,"y":150,"atMilliseconds":1800}
  ],
  "observeAfterStep": 2,
  "interrupt": {"action":"escape","atMilliseconds":1200}
}
```

Coordinates must come from the actual current app image. The optional
`observeAfterStep` still requires Capture VM and an image-capable model. Allow
enough time to observe the held app state before the interrupt; capture records
an observed interval and can miss a scheduled phase. Actual dispatch times and
app consumption are not inferred from the plan.

For native window changes, use e.g.
`{"action":"resize","width":640,"height":400,"atMilliseconds":700}` or
`{"action":"minimize","atMilliseconds":700}`. Schedule these by1000ms;
the last held step must precede the interrupt and final up must follow it.
These actions additionally need the existing Control app window and Run
permissions, `windowControl=true` on that original run, and its exact native
controller grant. Minimize is an actual own-window operation. It does not
fabricate a focus-lost event or prove that the app consumed one. Restore is a
separate explicit own-window action after the gesture finishes.

The unprivileged host validates the entire plan before input. It reserves a
monotonically increasing original window operation ID, prepares its exact native
request, and fsyncs the gesture intent including target/process, request, native
token and deadline before submission. The guest validates the prepared request
and remaining deadline before queuing a down. It submits that request once at
the interrupt and reads only that original operation if its receipt is pending
or lost. An applied native transition while release is still pending is recorded
separately from later composed-frame evidence. A late applied receipt after
release cannot retroactively confirm the held interaction.

After the native window action, only the original button release remains; no
move, replacement target or new input is sent to the changed view. Stop,
transport loss, unexpected view/process changes and the existing guest deadline
abort/release the original press. Guest RPCs retain their bounded native waits;
dispatch may be late and is reported as observed. The host saves original
receipts and never repeats an uncertain gesture or command. `heldAtDispatch`
means the controller queued down without a matching up yet, not proof of native
pointer capture or application consumption. Inspect the actual image/output and
native frame receipt before passing a configured check.

## Outside-client release remains a native integration boundary

Studio's gesture-v1 adapter queues owned app events using `guiPushEvent`. Sending
negative coordinates through that queue would bypass actual pointer routing and
would not qualify a native outside-client drag. Full0.88.107 / Kernel0.1.452
already supports app pointer capture; its host-input/capture APIs are owned by
the registered Desktop process, not this delegated Studio helper. Studio does
not replace that global owner or use global VM input as a workaround. A scoped
native Desktop delegation for these gesture plans is still needed before this
case can be automated. It remains open in app acceptance criteria.

The adapter uses the existing private SDK0.64.127 and Contract0.64.68 pins.
No kernel/Desktop/SDK upgrade, user app launch, Goal Play or session migration
is performed by installing Studio. Desktop/window/taskbar icon integration is
outside this change.
