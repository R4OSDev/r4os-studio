# Native subscription observations and account holds (0.8.53)

Check subscription limits in System → LLM Providers runs the pinned, unchanged
native CLI/SDK using only that provider's private authentication home. Native
auth status is checked before and after the SDK observation; account, plan,
backend, runtime, original request, browser ownership and provider revision stay
bound. Credentials remain native. This action never submits a model prompt.

The fixed control calls
`usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET({skipBehaviors:true})`.
It does not implement an OAuth HTTP client or scan other local transcripts.
Its ephemeral conversation directory is isolated from saved user histories.
Original authentication receipts also recover this bounded metadata request;
Cancel and failures do not repeat sign-in or start a model.

Provider and compact session views show reported windows, remaining percentages,
local reset times with timezone/countdown, receipt time and explicit stale,
partial or unavailable coverage. Unknown values remain unknown. Additional
server meters retain their scope and supplied severity. A countdown causes no
resumption. Cached GETs never contact the native provider or alter credentials.

Native rate-limit events are a separate source: their fractional utilization
and epoch-second resets are normalized independently from get_usage percentages
and ISO timestamps. Original owner/session/run/account bindings and events
survive reload. A warning/rejected quota event is not a replacement for the
original run or tool completion receipt.

## Qualified boundary

Actual isolated CLI/SDK checks with synthetic credentials and an owned TLS
endpoint prove the full auth/usage receipt path, numeric windows and disabled
extra usage without any model prompt. A separate owned fake Messages fixture
proves an actual warning event with 0.75 utilization and its original reset,
while the original tool/result completes. These are protocol checks, not real
subscription usage or billing evidence.

The pinned client's broad NONESSENTIAL_TRAFFIC setting also blocks its own
get_usage Data API request before HTTP. Authenticated SDK controls therefore use
the specific telemetry/error-report/update exclusions. Fixed environments,
private mounts, excluded plugins/tools/background behavior and native SDK calls
remain the boundary; arbitrary caller endpoints or OAuth-token HTTP calls are
not exposed. Empty offline foundation probes remain network-isolated.

## Runtime admission and limit stops

The pure admission policy rejects unknown/stale quota, an account/auth mismatch,
exhausted relevant windows and enabled or unconfirmed extra usage. The pinned
client has no qualified per-send overage-disable switch: actual account-level
extra usage must be disabled and remain disabled before eventual model use.
Hiding a command or interrupting after a charge is not protection.

Since0.8.52, qualified text models use this admission path. Two minimal real
Pro-subscription runs have confirmed native first-party auth, fresh usage with
extra usage disabled, Studio tools, same-history resume and numeric lifetime
retention after named session deletion. Model advertisements remain separate
from entitlement. No real account quota was deliberately exhausted.

Native subscription rejection and overage observations persist a verified
account hold, immediately close new tool admission and request original-worker
Stop. Already admitted effects retain their original receipts. A bounded
background observer also stops other admitted workers sharing the account;
each tool authorization checks the hold again. Unknown completion remains
protected. A Stop arriving after the terminal result is an idempotent close,
not another interrupt of an already closed native query.

The quota view exposes the hold independently of fresh numeric samples, and
prefers a newer per-send sample only with its original provider/revision/account
binding. Native event percentages and reset times may remain unknown. A fresh
zero-usage sample or a passed reset cannot clear the hold. After fresh admission,
only a new explicit send, explicit queue continuation, or the first human step
of a newly accepted Play can release it by compare-and-swap. An automatic Goal
step, timer, metadata read or restore cannot grant that authority.
Releasing one account hold retains its original receipt as an authorization
boundary: older queued inputs in other sessions still need their own explicit
continuation. Their original acceptance time is used, never a later dispatch
time. A new hold supersedes that authorization.

Generic request throttling and server errors have separate typed errors; they
do not by themselves prove exhausted subscription quota. Native errors use
fixed safe descriptions, never raw provider text or synthetic tool blocks.
The original result is drained and its actual error flag retained, even when
the native result subtype says success. Model errors do not select a replacement.

Native general retry/watchdog, non-streaming timeout, model-access and refusal
fallback controls are fixed in the pinned child environment. The CLI still
negotiates a streaming endpoint404 with one non-streaming request to the same
model: [official error reference](https://code.claude.com/docs/en/errors#api-returned-an-empty-or-malformed-response).
The controlled native model-refusal check observes those two requests with the
same human messages/tools, one Studio input and no effects; its native system
envelope can differ. This is not a qualified Studio automatic retry controller.

Actual unchanged SDK/CLI checks in owned filesystem/network namespaces prove
the model refusal, safe terminal error, native subscription rejection event,
retained prior tool effect and readable original completion. Focused host tests
cover shared holds, queue holding, fresh explicit Play and rejected automatic
continuation. Browser checks cover Held/unknown/reset display at1440/320px.
Actual quota exhaustion, paid usage and account changes were not provoked.
Auth/provider removal and the remaining live/direct/retry/overall integration
remain separate work. Existing Codex/API sessions, histories, pins and VMs stay
on their original bindings.
