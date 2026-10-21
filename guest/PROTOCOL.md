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
