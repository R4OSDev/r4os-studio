# Native Claude subscription authentication (0.8.54)

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
extra usage; text model access requires a fresh qualified native catalog and
per-send subscription/usage admission with extra usage disabled. The real
Pro-account text/tool/resume qualification is documented in0.8.52.

## Removing a connection

Disconnect first, then choose **Remove provider** and type its exact display
name. The DELETE request binds the original request UUID, provider revision,
name and browser owner. If its private auth home exists, the pinned native CLI
must independently confirm no active sign-in, complete logout, and confirm that
status again. These local removal checks run without network access. An unused
provider with no native home is retired without creating one or invoking a CLI.

The catalog identity is retired atomically with its terminal `removed` receipt.
It disappears from the provider list; GET and old auth receipts return410.
The initiating browser can still read its exact removal result. Old creation
receipts report `deleted`, clear the original form, and never recreate a home or
connection. Reading a lost result never repeats native logout. A stale browser
reading an old auth receipt reloads the list without signing in again.

Native logout alone owns credential removal; Studio never manually deletes
credential files. Private preferences, revisions, audit receipts and existing
conversations remain on the host. Their old provider/native-session identities
are not rebound. Pending queued text remains saved and is held at dispatch
without creating a run when its provider was removed. No user worker is stopped.

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

One auth operation per provider, at most two per coordinator, serializes Studio
logout/sign-in operations. Native refresh remains the CLI's responsibility.
Revision checks and durable original receipts prevent
request replay. A lost response is recovered through Read original request,
which reads the original result instead of starting another login. Cancellation
kills and confirms the owned process before recording cancellation; credentials
are preserved for an explicit subsequent native status check. Deadlines and
interrupted operations require that check before another sign-in, logout or
removal. Cancelled/expired receipts keep their original outcome and record the
later explicit status request separately. Original results remain readable even
when the two new-operation slots are busy, without inserting a phantom request.
Startup never
restarts authentication. Active/unbound bound workers prevent auth changes;
they are not stopped. Reserved/active/unknown credential leases also block auth
changes. An accepted auth marker prevents acquiring a new credential lease;
provider retirement rechecks outstanding leases in its final transaction.
Queued intents acquire no worker lease and retain their frozen account,
revision and native UUID; dispatch rejects a changed or removed provider.

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

The user connected a real Pro account and completed the minimal text/tool/resume
acceptance in0.8.52. In0.8.54, targeted store/HTTP/queue cases and the unchanged
pinned CLI additionally cover removal, exact-name confirmation, missing replies,
retired creation recovery, deadlines/status reconciliation and credential-lease
interlocks. Real React views are checked at1440/320 pixels with owned replies.
Two additional runs of the unchanged SDK/CLI in a closed namespace use owned
synthetic credentials, including an expired credential, and return401 from an
owned endpoint. Production admission and the original native input/result path
remain unchanged: concrete authentication failure, zero Studio tool effects,
same native UUID and readable terminal history. No Studio re-login or new run
is started. The CLI itself attempts native refresh and once repeats the same
model request after401 even with general retries disabled. This behavior is
distinct from Studio retry authorization. Real token revocation, successful
server-side refresh and billing are not inferred from these owned cases; the
user's real account is not revoked, refreshed or disconnected by this check.
Existing user subscriptions, native sessions, histories, project pins and VMs
remain unchanged. See [Claude-Subscription.md](Claude-Subscription.md)
for the immutable runtime foundation and [README.md](README.md) for rollout.
