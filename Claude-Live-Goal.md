# Private live GOAL query protocol (0.8.56)

This adds the native-query boundary needed by the pending0.8.23 live Goal work.
The public Save/Play controller, durable live execution ledger and UI wiring
are not yet connected. Normal workers do not enable this optional preparation;
the existing idle bounded Goal interface remains available.

A prepared query exposes the fixed report facet but denies it outside a Goal
input. `arm_goal` records a separately accepted execution ID, objective and the
fixed eight-step/900-second bounds while the original ordinary input is active.
It submits no prompt, performs no admission and starts no clock. Replaying the
same arm reads its receipt; changed authority is rejected. The original submitted
input is sufficient to record intent: the SDK's stdin echo may arrive only after
the server starts responding. That intent is not input acceptance.

`begin_goal` requires the original response's positive result and input receipt,
the same prepared query and the exact armed execution ID. It sends the saved
objective with a new human input UUID only after fresh subscription admission.
The frozen run/provider/native-session binding remains the ordinary binding.
The ordinary result stays retained separately, and its input/time is excluded
from the Goal's eight-step/900-second counters. The Goal clock begins only at
the positive Goal input echo. Later inputs retain the existing bounded
automatic-continuation protocol; the adapter never self-starts on a result.

Each input clears the prior model observation, so tool admission requires the
current input's fixed model evidence. `report_goal` is denied before the actual
Goal input and its receipt. Closing an armed Goal without starting it, denied
fresh admission or Stop during that admission preserves the completed ordinary
result without interrupting an already completed native query. Failed ordinary
results cannot begin a Goal. The private closure receipt separates the original
source result, live execution identity and whether a Goal input was submitted.

Focused protocol cases cover the safe boundary, repeat/change handling, current
model evidence, no automatic input, cancelled/unarmed/failed source paths and
Stop or refusal during admission. Existing bounded continuation and step-cap
cases still pass. The unchanged SDK0.3.312/CLI2.1.312 ran in an owned closed
filesystem/network namespace: one ordinary input, two Goal inputs, three native
input echoes/results, two report calls and one native query/session. The ordinary
result and readable final history were preserved. Auth/TLS/admission data in
that check are synthetic; it is not real subscription or public control proof.

The remaining controller must bind each accepted command to the original live
worker/configuration/native session, keep the execution contract separate from
the frozen ordinary config, and project activation only after the Goal receipt.
It must also handle revocation, queued-input priority, recovery and original
worker closure without sending another Play. These requirements keep23 open.
