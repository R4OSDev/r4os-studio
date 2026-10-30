# Live Studio GOAL with Claude (0.8.57)

New compatible ordinary Claude workers accept **Save** and **Play** while the
original response is running. Save stores a paused objective locally. Play shows
**After response…** and waits for that response's confirmed input and successful
result. It then submits a separate Goal input in the same native query and
conversation, after fresh subscription admission. Older workers must finish
before they can acquire this capability; loading a page never upgrades a run.

The saved objective, original scope and tool permissions remain unchanged. Each
Play is bounded to eight steps or 900 active seconds. Its monotone clock starts
at the new native Goal input receipt, excluding the ordinary response and wait.
Continuation inputs require their own admission and native receipts. A model's
complete/continue/blocked report alone cannot authorize another step or confirm
the original native result and tool effects.

## Original authority and input evidence

The public command names the exact original `targetRunId` and session revision.
The server binds the accepted intent to its original worker PID/birth/release,
configuration SHA-256, provider/account lease and native session. The frozen
ordinary run configuration is never rewritten. A separate live execution
contract and journal retain the Play UUID, objective, original command hash and
source response. Claude identities never enter Codex thread/turn fields.

The first Goal input includes a fixed host activation notice and the unchanged
saved objective. Its receipt hashes the complete submitted text; the objective
also retains its separate original hash. The notice makes the explicit Play
visible to the model. It grants no authority by itself: the engine independently
requires the accepted original Play, successful source result, actual input
receipt, fresh admission and current fixed-model evidence before allowing the
reserved `report_goal` facet. That status facet grants no project permissions.

Arming is only a waiting intent: it sends no input and starts no clock. The
original SDK input echo can arrive after the user presses Play. The actual
begin boundary still requires that echo and the completed ordinary result.
A background task processes the two receipts, avoiding a deadlock in the native
stream reader. The source run request ID stays original; Goal step IDs and the
execution ID separately identify the later inputs. The UI retains the original
saved objective as the human Goal message.

## Revocation and recovery

Queued messages take priority before Goal begin and after each completed Goal
step. Fresh admission rechecks their priority. Pause targets the attached Goal
execution on the same original worker and prevents continuation after the
current admitted step. Stop remains available while Play waits and closes
admission immediately. Neither path creates another query or resumes history.

Reload reads the original command receipt. Coordinator restart retains only
positively bound live worker executions; it never delivers a new Save/Play,
arm or begin. The still-running worker can drain accepted Pause/Stop revocations.
An accepted intent not delivered before its source ends fails without starting
anything. Missing/changed worker bindings and uncertain effects retain Unknown
and their original evidence, without replay.

A refused fresh admission preserves the completed ordinary result and readable
history. The native closure explicitly distinguishes the original source input,
source result, Goal execution and whether any Goal input was submitted. The
ordinary `promptSubmitted` flag cannot be used as Goal submission evidence.
No-input classification requires matching positive source and closure evidence.

## Verification and remaining work

Seven focused controller cases cover delayed original echo versus Goal clock,
source/worker changes, duplicate intent, late native refusal, Stop, live Pause,
queue priority and passive receipt recovery. Existing bounded Goal, original
input and quota-release cases remain compatible. Two native engine cases cover
the activation notice and refusal/Stop boundary.

The unchanged SDK0.3.312/CLI2.1.312 ran through the candidate production worker,
namespace, admission, original-worker socket, journal and clock. An owned closed
TLS/account case completed one ordinary input and two Goal inputs in one query;
a separate exhausted-quota case refused the Goal input, retained the source
result/history and created no Goal clock. Synthetic server/account facts in
these cases are not actual subscription entitlement evidence.

A minimal actual connected Pro check then completed the ordinary response and
one explicitly activated Goal step, including its report, result, readable
history and ended clock in the same native session. All project tools were
disabled; only the reserved status facet was used. Two earlier short diagnostic
attempts safely stayed Blocked because the model lacked an unambiguous Play
notice. The fixed notice resolved that observed failure; none was automatically
retried. Existing credentials were mounted without copying and their hashes
were unchanged. Only owned disposable project/session/history data were used.

The actual React hook, editor and controls were checked at1440/320px with owned
API responses: exact target/revision, waiting label, unchanged zero clock,
receipt reads and enabled Stop; no overflow or JavaScript errors. The320px check
also used Reduced Motion. These UI responses are not a public backend inference
proof. Full direct-message/retry and subscription lifecycle acceptance remain
open in0.8.23; this release completes its live Goal integration task only after
publication and installed readback.
