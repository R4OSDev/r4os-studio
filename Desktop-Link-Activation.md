# Native desktop link activation (0.9.11; fixes through 0.9.22)

Studio can explicitly activate the exact shortcut of a verified GUI deployment
through the native Desktop R4LNK path. Publication, icon display, native start,
frame readiness, process completion and cleanup have separate receipts. Viewing
options, publishing a link and installing Studio never start an application.

## Link-bound screenshots (0.9.22)

A native link job stores `desktopLinkActivation`, independently of ordinary
DESKRUN's `desktopLaunch`. Capture verifies the original saved canonical Prepare
request, its SHA-256, publication/link identity and exact native process
generation before requesting a screen image. The image retains that public link
activation as its own metadata; it has no invented DESKRUN request or window ID.
The actual controller window, geometry/focus and boot are observed before and
after capture. Image input/completion also retain the immutable link binding.
Missing or mismatching originals return a capture error. The fix is in the host
execution worker; guest helpers, application pins and historical jobs are kept.

## Original link request filenames (0.9.18)

The Exchange transfer guard accepts the native recovery helper's exact
`L[0-9a-f]{7}.BIN` filename inside the already verified package root. Both host
and guest retain the original execution UUID's lettercase. The former uppercase
filename rule rejected this internal file after a successful native Prepare,
before any Activate. Existing short filename rules, root binding, create-only
transfer and complete size/hash readback remain in force. No guest-helper or
project pin change is required; old jobs are not retried or rewritten.

## Use

Deploy the GUI R4X with **Deploy to desktop** using the current Studio helper.
On the completed publication choose **Run desktop link**. Project conversations
can instead call `studio_run_project` with `desktopLink=true` and the exact
published `deploymentId`, under the existing Run project permission. New accepted
runs use the installed tool catalog in the same conversation. Since 0.9.19 the
development coordinator also removes the two leftover generation checks for
`desktopShortcut` and `desktopLink`; the original active worker, permissions,
revision, pins and own-session artifact binding still authorize these requests.
The compatible guest must already be running and reachable through its assigned
private SSH transport. Neither action starts or updates a VM automatically.

A new deployment is required for `desktopLinkVersion=1`. Run arguments must be
empty: the published R4LNK owns its arguments and GUI policy. Native window
control delegation is unavailable for this activation path, so omit
`windowControl` or set it to false. Existing own-client capture/input permissions
and fresh process/window/frame checks remain required. Normal direct runs keep
their existing DESKRUN behavior.

## Original admission and verification

Before admitting a new job, the coordinator checks the original completed
publication, the derived own `C:\R4OS\DESKTOP\S<project-hash>.LNK`, exact link
bytes and the complete deployed APP.R4X hash/size through bounded read-only SFTP.
The checks run under a temporary VM lease, without guest writes. The execution
worker repeats them, including the original VM service invocation binding,
before Prepare/Activate. Foreign or edited links, uncertain publications, another
deployment, changed app bytes and arbitrary paths are rejected.

The original watchdog calls the public typed SDK `desktop_links` API:

1. Scope and Prepare bind the exact link bytes/path, watchdog process generation,
   native WINSVC service/epoch, deadline and an execution-derived intent.
2. The host verifies and durably saves the complete canonical Contract71 request
   and original publication/job/VM binding before Activate. A create-only binary
   copy in the private deployment is fully read back before activation.
3. The watchdog sends Activate once. Desktop itself validates and resolves R4LNK
   and starts its actual target through its native link path. Studio neither
   resolves the link into a substitute direct start nor sends global input.
4. Replies retain the original native request, actual resolved target/arguments/
   policy, Desktop and WINSVC identities, process generation and separate native
   prepared/accepted/starting/process/ready/ended/cleaned phases. Ready requires
   native frame/output revision plus the existing own-window observation.
5. Native ended/reaped evidence gates completion. Output availability, actual
   exit and helper cleanup remain distinct; unreadable retained output is marked
   incomplete. Release is accepted only with its confirmed original native
   cleanup receipt, followed by the existing helper closure proof.

The native admission deadline is at most30 seconds; application timeouts retain
their original bounded deadline. Watchdog control-loss cleanup also has a
monotonic time bound. A confirmed pre-start rejection may close without claiming
an application start. Missing helper cleanup stays protected and recoverable.

## Lost replies and recovery

The browser saves the original request/body and first reads that exact request
on explicit retry after reload or response loss. Idempotent resubmission uses
the same request, never a newer deployment or a fresh activation identity.
Agents use the existing own-session original-job lookup.

After a lost Activate/control reply, reconciliation uses only the saved original
request. A fixed `STHELP <execution-id> linkread` mode reads its deployment-local
binary copy and invokes native Status; it cannot Prepare, Activate, adopt,
Close, reap or release another process. The full canonical request and original
publication/job/VM bindings are checked before accepting the readback.
Readback alone cannot prove original helper cleanup or complete output, so it
leaves the job unknown until the existing full original closure or confirmed
VM-end proof is available. WINSVC/boot replacement or native retention expiry
stays stale/unavailable; there is no replay or automatic quarantine release.

## Qualified public sources and limits

The explicitly supplied integration versions were qualified from immutable
public sources and release-asset SHA256s, not from a Studio guest run:

- SDK0.64.134: `4542a3e558cfd0aa25936f02d722ddc7ea2f7fb1`.
- Contract0.64.71: `f825a0877e50335df72aab01e13e256ec1dddd08`.
- R4OS0.89.18 Full/Slim source manifest: Kernel0.1.454,
  Desktop0.1.200 `b52905da65862fdfee767b5bde67e5d40375be38`,
  WINSVC0.1.33 `c47cbce9084bf3dbfb59a1c58a7a6a6f428ee601`,
  DESKRUN0.1.5 `ff211821e18dda3c270e12649c29fd5ee6a63be5`.

Only new private helper builds bind the new SDK/Contract; existing user project
pins, deployments, frozen workers and sessions are preserved. The SDK manifest
names Kernel0.1.453 as its minimum; qualification here uses the complete reported
R4OS0.89.18 source set with Kernel0.1.454. No guest image was imported or replaced.

The earlier0.9.5 boundary used SDK0.64.127/Contract0.64.68/Desktop0.1.198, which
lacked this link contract. The new link protocol does not provide predeclared
correlation for ordinary DESKRUN starts, nor restore historical operations that
never saved a native request. Roadmap0.9.2 tasks2/3 remain open for that gap.

Build/TypeScript/lint, Python AST, unchanged old declarations and pinned private
helper compilation are the validation scope. No tests, fixtures, inference,
application/VM runs or positive native activation acceptance are claimed.
