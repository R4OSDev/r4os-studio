# Studio development protocol 1

This is a Studio-owned adapter contract. It is not an R4OS ABI extension, a
QEMU Guest Agent implementation, or a replacement for SDK component checks.
The host, worker, data and guest versions/limits are declared in
`shared/development-host.json`; public browser projections are declared in
`shared/project-development.d.ts`. Host and guest implementations follow in the
next development increments. Qualification alone exposes no remote execution API.

The broker accepts fixed build/deploy/execution/read/stop/capture/input operations
scoped to the authenticated project. It resolves the VM from stored project
settings. Requests contain opaque owned artifact/deployment/job IDs, expected
project/settings revisions and a stable request UUID. They never supply an
arbitrary host, VM, host path, SSH shell command or QMP method. A repeated request
with the same payload returns the same record; changed payload is a conflict.

Each job binds the source snapshot/manifest hash, complete component pins,
artifact package hash, adapter release, parent agent run/session when applicable,
and target VM revision/image hash. Executions additionally bind the VM boot
identity, guest-helper instance, protocol/binary hash and generation-bound guest
process handle. Native u64 generations are decimal strings in JSON.

The private guest control channel uses bounded UTF-8 JSON lines. Requests have
`version`, `requestId`, `instance`, `operation` and a strict operation-specific
`payload`. Replies echo those identities and contain `success`, `result` or a
bounded `error`. The fixed operations are hello, launch, inspect, input and stop.
File packages use the separately qualified SFTP path; they are not embedded in
control frames. Deployment directory/entry/hash and process identity are resolved
and validated by the broker and helper, never taken as free model-supplied paths.
Only the active instance can operate on its own generation-bound process.

The first authenticated hello describes available APIs, image/runtime identity,
helper instance and protocol. A console helper must import both R4SYS and R4DESK:
`program_spawn_with_console_host_handle` belongs to R4DESK. Child console output
must be isolated from control output; completion bytes are explicitly collected.
The transport preserves actual console output semantics rather than inventing a
separate stderr stream. OpenSSH multiplexing across completed commands is not
assumed: the qualified SSHD closes the transport after its session channel ends.

No host/guest reply is accepted as a completed build, deployment, process or test
merely because its request was accepted. Host intent precedes effects, publication
and guest receipts precede success. Multi-step transfer and process creation are
not asserted to be one cross-host transaction. Ambiguous publication/start/end
retains effects and becomes unknown; no automatic replay after a lost reply.
Current connection/instance loss cannot be repaired by trusting a reused PID.
Host boot does not initiate new inference, builds, transfers or guest launches.

Build, deployment, running execution and check verdict are separate states. A
check records explicit criteria, observed evidence and passed/failed/inconclusive;
an agent's visual judgement is distinguished from host assertions. Output is
bounded and cursor-based; image data is held as protected evidence and sent to
qualified native image-capable tool consumers under the frame budget. Arbitrary
Markdown images and executable model HTML remain disabled.

User Stop closes further admission, cancels owned host work and requests bounded
guest cleanup independently of the model's stop-tool permission. Only owned
generation-bound children/services are closed or killed. A live GUI/service job
retains a lease/watchdog and explicit stop until its actual end. A VM reset,
delete, force-stop, image switch or access reconfiguration cannot silently race
that lease. No downloaded root installer or arbitrary administrative guest shell
is part of this contract.

## Retained desktop evidence v1 (0.8.72)

New helpers declare desktopEvidenceVersion1, with unchanged control/watchdog
and transport versions. The private evidence operation uses the generated
Contract68 128-byte token encoded as base64, lossless decimal generations and
original service outcomes. Reserve/Offer/ACK are host-controlled steps with
durable intent/token records between them. Status resolves an uncertain native
RPC. The original DESKRUN epoch is never replaced by a later STATUS scope.

A fresh `STHELP <execution UUID> evidence` reader accepts only Status/Read/Release
from its exact deployment-local E<UUID-prefix>.JSN request; it cannot Reserve,
Offer, ACK, spawn, reap or mutate a window. Host recovery verifies the original
boot and helper bytes and serializes this fixed file under the VM lease. The
reader returns the original completion and bounded output chunks. Recovery
retains the previous host output and its own original transport records.


## Own Desktop window control v1 (0.8.73)

New helpers also declare dragInterruptVersion1. A profile17 gesture may include
one Escape or prepared own resize/minimize between the last held step and its
final up. The complete native command is saved by the host before input; its
operation is submitted once and status reads never repeat it. Apply while the
original release is pending and later composed-frame proof remain separate.
Unexpected changes, Stop, deadline or lost control release the original press.
Outside-client capture routing remains unsupported; no Desktop-owner takeover.
Existing gestureVersion1 and older declarations stay compatible. See
Drag-Interrupts.md for admission, timing, permissions and evidence limits.

New helpers declare windowControlVersion1 without changing the existing private
control/watchdog transport versions. Only a profile16 session with its explicit
window permission and per-run opt-in requests DESKRUN controller delegation.
The delegated controller is the actual watchdog's complete native process handle.
The original launch epoch/request/grant binds the one owned window incarnation;
no public request supplies a VM, PID, window ID, position, flag or native token.

window_bind is read-only Status of that original grant. window_prepare obtains a
fresh Current state and prepares a bounded resize/minimize/restore request with
an operation ID and native deadline. The host saves the exact192-byte request
before window_command. The helper permits one submission matching every prepared
byte. window_status queries only the prepared original operation after submission;
scope-only Status cannot overwrite an outstanding receipt. Another command needs
the previous command's confirmed composed frame. Applied is immutable and Current
is live. Window view revisions invalidate images even after restoring the same
geometry. Unknown effects remain protected; no automatic repeat or new app launch.
window_release returns the original native release outcome before helper finish.

Since0.8.80 the host reserves strictly increasing unsigned64-bit operation IDs
per execution before window_prepare. The UUID request key remains independent.
The next number exceeds both the last saved window receipt and the durable
allocation counter, including earlier failed preparations. Status cannot rewind
that counter; exhaustion fails before preparation. WINSVC's original grant and
the helper's one-submission guard remain unchanged; existing deployed helpers
use the corrected host allocator without replacement.
## Explicit project desktop shortcut (0.8.84)

The normal helper handshake adds `desktopShortcutVersion=1` when the required
public file stream/checked atomic/checked delete operations are available.
`STHELP.R4X <original-job-UUID> shortcut` is one bounded, one-shot desktop-link
publication, separate from the process controller. It reads only DSKIN.JSN beside
itself, verifies the deployment ownership receipt and its own derived module
directory, and targets only that directory's APP.R4X. The project-derived fixed
Desktop link uses POLICY=gui and ICON=INTERNAL. No generic path or shell input.

Original host backup/intent and the guest create-only DSKINT.JSN marker precede
mutation. Existing link bytes must match the saved own receipt; a checked native
atomic replacement verifies old/new bytes with the native size/checksum contract,
then full readback and checked backup cleanup complete. DSKOUT.JSN and stdout
carry the same bound result. The host reads both and the exact link bytes before
recording success. Lost replies are observed from this original result, never by
resubmitting the helper. Unknown stages/backups remain protected. The receipt
does not confirm desktop visibility, app launch or application consumption.
## Independent watchdog launch v2 (0.9.12)

Qualification and the controller's sequence-zero hello add
`watchdogLaunchVersion=2`. The relay starts its exact own `STHELP.R4X <UUID> watch`
using the public generation-bound console-host API with an explicit terminal
console. Native background publication is the detach boundary; the watchdog does
not inherit SSH's console. No SCM entry is installed, started or removed. The
old STWATCH binary remains an immutable compatibility artifact, unused by v2.
`bootstrapUsed=false` and legacy `bootstrapRemoved=true` mean that no bootstrap
registration was created. Watchdog heartbeat, timeout, original process binding,
application cleanup and final watchdog-end confirmation remain unchanged.

Before spawn, a unique own B<UUID-prefix>.JSN journal records intent and relay
identity; after the one atomic handle spawn it records the exact watchdog handle.
The normal mailbox hello must match that handle and generation. Q/A/B collisions
fail without overwrite. A versioned negative startup response identifies the
original phase, native code and whether no child was created. Only a fully bound
positive no-child/no-application-start failure may close that startup scope;
errors after spawn and lost responses remain unconfirmed. Raw initial response,
bounded SSH stderr and the final local SSH exit are private host diagnostics;
a host-killed SSH client never supplies an application exit code.
