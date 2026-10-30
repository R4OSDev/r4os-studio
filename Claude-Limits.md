# Native subscription observations (0.8.21, partial acceptance)

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

## Remaining model and lifecycle stages

The pure admission policy rejects unknown/stale quota, an account/auth mismatch,
exhausted relevant windows and enabled or unconfirmed extra usage. The pinned
client has no qualified per-send overage-disable switch: actual account-level
extra usage must be disabled and remain disabled before eventual model use.
Hiding a command or interrupting after a charge is not protection.

This policy is preparation, not an enabled model gate. The production worker
still has its closed admission default and no publicly eligible Claude models.
Shared account holds, real worker admission/limit stopping, Goal/queue/retry
integration and deliberate continuation remain open with the subsequent model
and lifecycle stages. Tasks 3/4 and final acceptance remain open; a real human
account/refresh/expiry/revocation acceptance is also still outstanding. Existing
Codex/API sessions, native histories, project pins and VMs remain separate.
