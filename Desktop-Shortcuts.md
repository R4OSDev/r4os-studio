# Historical implementation — retired in 0.9.26

Studio no longer publishes or owns desktop links or offers managed link activation.
Only original receipts and immutable old releases remain. Do not execute the
following historical workflow. Use [Project-VM-SSH.md](Project-VM-SSH.md) and
the current short project guide for a user-requested guest shortcut.

# Project desktop publication (0.8.84; replacement recovery 0.9.20)

Since0.9.20 the private helper interprets checked deletion using the pinned
SDK0.64.134/Contract0.64.71 constants: deleted is1, not_found is0, negative
results are errors. It retains the exact native result and failure phase in
stdout and best-effort create-only DSKERR.JSN after its original intent marker.
Final link readback and stage/backup absence still precede successful DSKOUT.
The additive diagnostics handshake is version1; desktopShortcutVersion remains1.
Future ordinary deployments carry the corrected helper. Previously deployed
helpers, original receipts and all application component pins are preserved.

The previous helper's hash-bound, positively recorded exit113 is a special
recovery case when native DSKOUT is absent. **Reconcile receipts** requires the
same VM revision/image/service invocation, original request and DSKINT bytes,
full SHA-256 readback of every deployed file including the original helpers,
exact intended link bytes and absent TMP/BAK. Reads are guarded by a current
QMP boot observer; a replaced observer does not attest original boot continuity.
The host saves a separate `original-desktop-current-files` observation and
publication receipt. It records the missing native completion and original
helper exit113, with null job exit. It does not fabricate DSKOUT, replay the
publication, clean up files or start APP.R4X. Other missing/uncertain replies or
any mismatching evidence stay protected. Original run/tool failures and previous
job state remain in their original history/recovery journal.

The historical description and initial component qualification below remain
applicable to their stated versions; the host observation above is an additional
explicit proof source for the identified legacy helper only.

Completed GUI R4X builds and deployments offer **Deploy to desktop** in their
development card. The browser submits a normal, revision-bound deployment with
`desktopShortcut=true`. It stores the original request before submission; an
uncertain reply is retried with exactly that request, never a newer artifact.
No VM or project application is started by this operation.

New project sessions use profile18. `studio_deploy_project` accepts the optional
boolean `desktopShortcut`, under the existing Deploy project permission and
original session/artifact ownership checks. Omitted/false preserves the ordinary
deployment behavior. All17 earlier project tool declarations remain unchanged;
existing conversations can use the browser action, or a new session for the
agent option. Current development guidance explains the icon path on subsequent
authorized runs without modifying saved prompts, histories, Goals or queues.

## Native path and ownership

Notepad's manifest uses `ICON=Assets/Desktop.ico`. SDK builds the first ICON into
the R4X as type1/index0. Distribution's `C:\R4OS\DESKTOP\NOTEPAD.LNK` selects
`ICON=INTERNAL`; Desktop reads this resource without launching the application.
A window-icon setter is unnecessary for this case. Taskbar/window icons are
separate. See the exact Notepad/distribution/Desktop sources in the source table
below. ICO display is32x32; the reviewed decoder supports uncompressed8/32-bit
DIB images. Missing ICON resources use Desktop's generic application fallback.

Studio owns exactly `C:\R4OS\DESKTOP\S<7 uppercase project-SHA256 digits>.LNK`
per project/VM. The label is the project name reduced to supported printable
letters, digits, spaces and `._()-`, at most64 characters; module name is the
fallback. The target is the exact selected verified deployment's APP.R4X.
Ordinary later test deployments do not change that target. Same-name projects
retain distinct project-derived identities; a short-name collision is refused.

SSH system-path write protection stays enabled. The newly deployed private
helper exposes `desktopShortcutVersion=1` when its required public native file
operations exist. Its single `shortcut` command reads only DSKIN.JSN beside its
own module, verifies DEPLOY.JSN ownership and its own exact project/deployment
directory, derives the link path itself and never accepts arbitrary target paths
or commands. It never launches APP.R4X or controls Desktop input.

Host and guest compare an existing link byte-for-byte with the original private
ownership receipt. A foreign or edited link, existing stage/backup, unconfirmed
previous publication or different guest identity blocks replacement. The host
persists the previous content and complete intent before one command submission.
The helper creates a request marker before mutation and uses create-only file
streams for its stage, native `file_update_atomic_checked` with old/new size and
FNV-1a checksums under the filesystem gate, full byte readback and checked backup
cleanup. The old bytes remain in the host's original DeployWork evidence. Short
TMP/BAK siblings are used by the native transaction and removed after success.

The native DSKOUT.JSN result and host receipt bind project, VM, original job,
deployment, target and content. Missing acknowledgements remain unknown and
block later desktop publications. **Reconcile receipts** reads only this
original saved result and exact link/stage/backup paths on the original VM service
invocation. A coordinator restart does not invalidate that process identity;
it never invokes the helper command again. Missing/damaged evidence stays
protected. No automatic rollback, restart, repair or repeated publication.

## Evidence and boundaries

`desktopShortcut.fullReadbackVerified` confirms the link bytes and native cleanup.
`iconEmbedded` reflects icon/index0 in the original artifact inventory. Neither
proves visible Desktop consumption or launch through the link:
`consumerVerified=false`, `guestVerified=false`, `applicationStarted=false`.
Studio shows these limits and teaches agents not to mark a desktop acceptance
complete from a build or publication alone. Own-client input/screenshot tools do
not provide global Desktop control. No user project acceptance is changed.

| Component | Bound version/revision | Relevant source |
| --- | --- | --- |
| SDK/private helper |0.64.127 / fbb5041487441473612d04d3166bcfa21f3d555f | r4os/r4sys.zig, file_stream.zig, module_manifest.zig, ico.zig |
| Contract |0.64.68 / 4c96b21df75662ca6a3af3c8ee332c342e2db185 | public file_update_atomic_checked, file_delete_if_match and stream operations |
| Full/kernel |0.88.107 /0.1.452 / d291f74a25b8ad67f0b6c45b5b3e365a51a25900 | Rust/program/system/atomic.rs, Rust/update/atomic.rs |
| Desktop |0.1.198 / 0a5b341ce3253cb073d3760b7ad0dea5732cf84b | shell/icon_source.rs, persistence.rs; render/icons.rs |
| Notepad |0.1.19 / 4ca6f20cb38d5c5c61621d1f0b69359a37c8e106 | module.R4MF |
| Distribution |0.88.107 / c11c88563c1a9567d5b4c5c666da72aed71d14ef | Injection/R4OS/DESKTOP/NOTEPAD.LNK |
| SSH service | dba200989d635f0ba0c7657ad80c369a6fc87d32 | src/main.zig: protected system writes, create-only SFTP publication |

Application component pins are unchanged. Guest operations need a running,
SSH-ready assigned VM and the verified current helper. Browser rendering and
request persistence run in the web app; guest file publication runs in the
bounded unprivileged development worker/private helper. Additive updater v18
support uses `scripts/agent-sessions/install-desktop-shortcut-support.py` with
its checked predecessor hash, without bootstrap initialization or VM stops.

Direct implementation without roadmap changes, tests, fixtures, model calls or
user app/VM runs. Static Studio checks and pinned private helper builds do not
qualify an actual guest publication or visible desktop icon.
