# Native Claude subscription authentication (0.8.19)

System → LLM Providers → New Provider offers **Claude · Pro / Max subscription**.
Add a name, then Connect Claude. Open the short-lived native sign-in link,
sign in to your own plan, and paste the complete confirmation code (including
its state after `#`). The pinned native client exchanges and stores it.
Reconnect starts a separate explicit native sign-in; Check provider status runs
only native auth status. Disconnect has a named confirmation and invokes the
native logout in this provider's own directory. No model prompt is submitted.

Only native `authMethod=claude.ai`, `apiProvider=firstParty`, a Pro/Max plan,
account identity and the bound configuration directory qualify as connected.
API key/helper, bearer-token, cloud, console or unknown-plan authentication
cannot qualify. Status is timestamped native evidence, not a perpetual account
or entitlement guarantee. Every future model admission must recheck its bound
native account and billing source. Subscription credentials alone do not stop
extra usage; model access remains disabled until session/tool and limit/overage
qualification in0.8.20–0.8.23.

## Host and browser boundaries

The existing unprivileged coordinator starts only the three fixed commands
`auth login --claudeai`, `auth status --json`, and `auth logout` from the exact
hash-pinned Claude runtime. No caller chooses executable, flags, URL, account
profile or environment. Bubblewrap provides an empty working directory, private
HOME/configuration, read-only executable/system libraries and TLS/DNS files;
no project sources, foreign login, host managed policy, settings sources, proxy,
cloud/API credentials, plugins, tools or model input are passed to this child.
Auth commands require network for the native OAuth flow; the separate SDK
metadata probe remains network-isolated. Auto-updates and nonessential traffic
are disabled. This installation targets Linux x64/glibc.

Native state lives under
`Data/LLMProvider/ClaudeSubscriptions/<provider-uuid>/{Home,Config}`.
Directories are0700 and regular files0600, owned by the service user. Links,
foreign ownership and changed private modes are refused while preserving data.
The CLI alone reads/writes/refreshes its credentials. Studio stores only provider
identity, safe account/status projections and original request receipts in its
private provider catalog. It never copies tokens into a second auth database,
workspace, browser, tool channel, statistics or application logs. Session history
will receive its own private binding in the session adapter.

HTTP uses the existing provider-browser session, allowed Host/Origin and CSRF
checks. A native authorization URL is accepted only at the pinned native Claude
OAuth origin/path with its PKCE/state and native code callback. The live URL
and code handoff are visible only to the initiating browser session and remain
in memory. URL lifetime is bounded to five minutes. Codes are submitted once,
matched to that exact live state, and cleared from UI memory after handoff.
Browser storage contains only original request UUIDs. No automatic login,
logout, retry, model start or account switching occurs on page load.

## Concurrency and original outcomes

One auth operation per provider, at most two per coordinator, serializes native
refresh/logout/sign-in. Revision checks and durable original receipts prevent
request replay. A lost response is recovered through Read original request,
which reads the original result instead of starting another login. Cancellation
kills and confirms the owned process before recording cancellation; credentials
are preserved for an explicit subsequent native status check. Deadlines and
interrupted operations require that check before another sign-in. Startup never
restarts authentication. Active/unbound bound workers prevent auth changes;
they are not stopped. Queue/worker credential leases and their final acceptance
remain part of the session/lifecycle integration in0.8.20/0.8.23. No provider
removal endpoint is offered at this authentication-only stage.

The coordinator does not switch its release while an auth job or SDK probe is
active. The SDK probe now has a dedicated0700 `ClaudeControl` directory under
the existing agents root; it does not change permissions on old run storage.

## Validation and remaining acceptance

Focused store/auth/HTTP cases cover original ownership, revisions, stale input,
code/state binding, duplicate handoff, interrupted recovery, cancellation,
foreign authentication rejection, private path/link checks and no token/code/URL
persistence. Actual unchanged pinned native CLI commands were run in an owned
empty filesystem with no network: status, generated native OAuth URL, confirmed
cancellation, logout and status. No account code, token or model prompt was
submitted. Actual React components are checked at1440/320 pixels using controlled
HTTP fixtures, separately from protected backend HTTP cases.

An actual human Pro/Max login, native refresh/expiry/revocation and final bound
worker/queue acceptance remain open. Synthetic account metadata is not proof
of a real subscription. Existing user subscriptions, native sessions, histories,
project pins and VMs remain unchanged. See [Claude-Subscription.md](Claude-Subscription.md)
for the immutable runtime foundation and [README.md](README.md) for rollout.
