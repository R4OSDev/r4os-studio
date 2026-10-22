# Studio guest execution adapter

The pinned SDK builds two private modules from these sources: STHELP.R4X
(console transport / independent watchdog) and STWATCH.R4X (short-lived manual
bootstrap service). No OS workspace,
SDK fork, global autostart configuration or Studio pins in the SDK are required.

Studio protocol 1 uses a host-generated execution UUID and strictly increasing
request sequence. Control version 2 / watchdog version 1 support one start,
status/output, exact-generation console input, stop and finish. Requests are
limited to 4 KiB; output frames stay below the guest's 16 KiB console tail.
The relay parses a small typed envelope, without allocating another JSON tree
for the encoded output. File reads accumulate short transfers to a bounded size.
Lost acknowledgements never cause an automatic start/input replay. EOF is not
an implemented guest console operation.

The console client communicates with its independent watchdog process through two
nonce-bound Qxxxxxxx.JSN/Axxxxxxx.JSN files inside the verified deployment.
Existing files/services refuse admission. The bootstrap starts an unlinked
console host and removes its own service record before application admission,
leaving the guest's limited service slots available for the project service.
The watchdog owns the project process,
checks heartbeats (15 seconds), enforces the application limit (at most 300
seconds), requests Close, then kills only the exact owned generation. Its final
receipt remains available after SSH loss. Normal finish confirms watchdog exit
and removes any owned project service. Interrupted bootstrap records are
preserved for explicit, scoped recovery; they never autostart.

The child receives the deployment directory through R4OS CWD and an opaque
bounded R4OS argument string. No POSIX cwd or shell expansion is implied.
Console output is one combined transcript, with explicit loss indication.
Native completion supplies exit code/reason and sequence when available. The
Desktop can consume GUI completions first: exact-generation disappearance then
confirms closure, while the exit code remains unknown. No success is inferred.

The two image-pinned Desktop hosts adopt a GUI after its own public process
window binding is assigned. Only that process is marked; the Desktop chooses
its available slot. WINSVC snapshot plus a rechecked process generation confirm
visibility/focus. Services use their immutable project module name, manual
start, checked path/incarnation and endpoint status. Foreign services remain
untouched. Console descendants linked by R4OS are covered by native tree stop;
independently launched services or GUI processes are outside that tree contract.
Library, driver, protocol and subsystem execution require separate qualified
hosts and remain unavailable. Original SDK notices remain alongside the source.

0.3.23 extends the same control contract with generation-owned logical GUI input
and an explicit service self-test. GUI input checks WINSVC visibility/focus and
the current GUI revision before dispatch; the host additionally requires a recent
job-bound image. Keys are bounded logical key-down events; a click queues both
down and up, with an owned-generation release retry. No global QMP input, physical
held modifiers, paste, arbitrary service operation or guest shell is exposed.
Service operation 1 runs once with a 500 ms deadline and at most 512 reply bytes.
Its response is compared with explicit host settings, separately from readiness.
