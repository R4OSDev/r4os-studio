# Desktop launch argument budget (0.8.42)

The canonical DESKRUN command builder now exposes a read-only byte budget:
112 UTF-8 command bytes after SSHD's 15-byte Terminal wrapper, including flags,
quoted verified path, spaces and optional short WAIT. It reports fixed/argument/
required/remaining bytes and overflow without returning argument contents. The
native 5000 ms default avoids an unnecessary WAIT flag; shorter deadlines are
calculated using the actual flag length. Admission and the final rebound worker
check use this same calculation. Oversize arguments are rejected before a new
job/controller/quarantine, never shortened, split or retried automatically.

Options publish fixed byte counts and saved-budget metadata only for a verified
Desktop deployment matching current project pins/revision, VM/image/revision
and a connected original boot observer with matching process identity. A missing
or changed binding reports unavailable rather than a guessed safe capacity.
Run & Test counts draft arguments with UTF-8 TextEncoder and those canonical
fixed counts, showing required/allowed/remaining bytes and explicit overflow.
Project/settings/VM revisions must match the saved binding; settings save
refreshes options. Deployment tool receipts expose the same budget before Run.
Original execution admission rejects oversize input before INSERT and retains
idempotent old receipts; workers recheck the actual rebound target before start.

Runtime guidance explains the native limit, saved budget and required explicit
app/SDK contract for argument-file alternatives. No general shell/SSHD wrapper or
argument-file transfer is invented. Host Rust build support does not establish
a native guest compiler.

Five focused checks reuse the original hotfix boundaries and cover multibyte
arguments, 99/999/1000/4999/default WAIT lengths, missing/changed bindings, no
new job on overflow, admitted budget and original-request replay. Python AST,
build/TypeScript and lint passed. No guest/application start or user VM action
was used. Evidence: Research/R4OS/Roadmap-Implementation/0.8.42/.
