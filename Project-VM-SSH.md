# Project VM SSH (0.9.25)

`studio_run_vm_command` submits one free native R4OS command to the VM currently assigned to the project. Studio keeps the host, private forwarding, login and host key internal. The local agent terminal remains without networking; Remote Hosts are a separate service. No artifact, deployment, private guest helper or desktop receipt is required.

The command needs its own **Run VM SSH command** switch in Session Tools (enabled by default, including existing sessions at the next normal catalog capture). Admission verifies the current project/session, frozen permission, worker PID/birth, revisions and VM assignment. Existing accepted contexts keep their original tools. The VM must already run with Network and development access enabled; SSH never starts it.

Use one R4OS Terminal command of at most **112 UTF-8 bytes**, including paths, spaces and arguments. Studio rejects control characters, invalid UTF-8 and oversized input before admitting effects; it never shortens input. The bound SSHD builds `/NOAUTOEXEC /C <command>` in its native argument buffer. Native guest permissions and SSHD behavior remain authoritative. There is no POSIX shell translation, command allowlist, stdin or PTY.

The tool returns the original durable development job immediately. `queued`/`running` is acceptance/progress, not a successful command result. Use `studio_read_development_job` for the same job, with `view=output` and optional `channel=stdout|stderr`; each channel has its own byte offsets. A lost admission response is recovered using the session job lookup and its original request/run/tool-call identity, never by running the command again. Existing job cards expose progress, output and Stop.

Each channel retains its first 1 MiB, with exact captured and received byte counts and a truncation flag; it continues draining after the quota. The combined diagnostic log is bounded to 2 MiB. Output replacement decoding is identified by the ordinary job-page encoding/base64 fields. An SSH exit other than 255 or a local signal confirms the command-shell return and its exit code, including nonzero failure. It does not prove detached descendant completion or application correctness. SSH255, a lost transport, observer failure or client Stop retains `unknown` and protects the VM from new effects until original evidence or an explicitly confirmed VM end resolves it. Stop receipts attest the **local SSH client** only. Positively pre-command readiness/permission/network/spawn errors do not leave a quarantine.

SSH and ordinary development jobs share the project admission lock, cross-process VM reservation, update exclusion and unknown-effect quarantine. Original command, owner, target/boot/invocation, output and terminal receipt are saved before any reconciliation. Reconciliation reads originals or confirms VM end; it never submits another command. No total command time limit is added. The dedicated unprivileged worker retains the normal resource and access restrictions, with `RuntimeMaxSec=infinity`; the normal VM/build worker deadline is unchanged.

Host setup, once: `python3 scripts/project-development/install-ssh-support.py` as root. This adds only the fixed SSH worker template and its narrow start/stop Polkit rule, then reloads unit definitions. It does not reinitialize bootstrap or restart any running service, worker or VM. Regular release installation remains through Studio Updates.

Validation for this release is source/AST, product build, TypeScript and lint plus installed readback. No test suite, fixture, project/VM test, model inference or guest command was run. Positive native SSH usage and transport-loss behavior remain open runtime acceptances.

## Requested desktop links (0.9.27)

The bundled short guide lives in `shared/project-vm-shortcuts.txt` and is also
part of the default `shared/system-prompt.json`. Effective project instruction
composition removes only exact duplicate bundled blocks and supplies one copy
when the frozen declared catalog and permission include the SSH tool. Otherwise
it supplies a retirement notice, with no guest-write capability claim. It works
independently of Read development job permission. No stored custom text, prompt
revision/hash, accepted run, existing thread or Skill Manager source is changed.

The source contract is R4OS0.89.18's Terminal8bd47792a3a6c3585bce8d5c0bed4d9c2e743179
and SSHDdba200989d635f0ba0c7657ad80c369a6fc87d32: builtin ECHO redirection uses
fileWrite/fileAppend, TYPE uses fileReadAt; SSHD's direct SFTP/SCP system-path
guards do not gate the Terminal exec path. Native filesystem errors remain
authoritative. This source qualification is not a live permission or desktop
appearance/activation test. No native protection is disabled and no guest
commands were executed for this guide.

Output metadata clarification (0.9.27): each selected channel reports its own
1 MiB limit and actual truncation. `ssh.outputComplete` describes received SSH
streams, with `outputCompletenessScope=received-ssh-streams`; it never attests
full native process output. `nativeOutputComplete` stays null unless SSHD
explicitly reports lost console bytes, in which case it is false and
`nativeOutputLossReported=true`. The original command is included even in the
initial compact acceptance result. No terminal receipt or guest effect changes.
