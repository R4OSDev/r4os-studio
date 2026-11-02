# Original Desktop launch receipts (0.9.2)

Each new Desktop launch records a durable host correlation ID before submission,
bound to its job, execution, deployment, VM invocation and target. It is explicitly
**not** a native DESKRUN request identity. The receipt exposes bounded transport
metadata (local SSH PID, actual status, timing and byte counts), not arguments,
credentials or raw stderr. The private original stdout/stderr evidence remains
unchanged and separate from the sequenced guest-control loss diagnostic.

A failed independent controller heartbeat no longer cancels the already submitted
DESKRUN response. The original SSH reader finishes within its existing deadline;
any received native request key is saved before propagating the controller error.
No start is retried and no replacement controller is created.

Reconciliation can recover a valid native request from its original saved stdout
after checking the exact launch command, original job/deployment/target/settings
and controller identity. This is metadata only: it does not adopt a process,
confirm process end or clear an unknown effect. Damaged, missing, foreign or
inconsistent receipts stay protected. Old frozen histories are not rewritten.

The recorded incident has an empty DESKRUN stdout/stderr and SSH exit255; it
cannot supply a native request key. A host UUID or missing ACK cannot establish
whether native admission happened. Full resolution of this case still requires
a qualified native predeclared request/lookup or an original completion receipt.
The current CLI adapter does not invent such a native API or mark absence as
not-started. That native correlation/positive acceptance remains open.

Source/receipt inspection, Python AST and Studio build/TypeScript/lint are used.
No tests, application/VM runs or inference were performed.
