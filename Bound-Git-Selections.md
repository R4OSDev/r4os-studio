# Read-only Git inspection and explicit large selections (0.9.8)

New `studio-tools-v22` conversations have **Read Git status, diff and jobs**,
separate from **Push project to GitHub**. Existing thread declarations and
permission choices remain unchanged. New Read permission defaults like other
read tools; Push retains its existing trusted-repository default and independent
switch. A read never grants Push or runs commit/fetch/pull/push/reconcile.

`studio_read_project_git` supports these views:

| View | Original inputs and result |
| --- | --- |
| status | Initial read returns an immutable snapshotId, repository/branch/base, file statuses and hashes. Continue with snapshotId/nextOffset. |
| diff | snapshotId/path identifies a frozen bounded diff. Continue exact UTF-8 byte nextOffset; captureTruncated is separate from hasMore. |
| select | snapshotId and an explicit reviewed files array produce selectionId and a paginated preview. No source or Git job is changed. |
| selection | selectionId/nextOffset reads the same immutable explicit selection. |
| job | requestId reads the original own-session Git job, including unknown publication state, without replay or reconcile. |

Pages contain at most25 entries and12KiB serialized output. Diff capture is
128KiB per file and each page has at most6KiB serialized text. Selections allow
1..512 explicit changed paths, at most65536 aggregate UTF-8 path bytes. Existing
source quotas remain10000 files/256MiB total/32MiB per file/1024 bytes per path.
Private immutable preview storage is bounded to8192 documents/256MiB per project;
original evidence is retained when full. These limits cover a coherent130-file milestone without unlimited expansion or
automatic splitting. Renames show both paths and require selecting both.

Snapshots and selections are immutable hash-checked private metadata, bound to
project, session, original run, frozen repository identity/revision, actual branch,
HEAD, source inventory hash, statuses and exact selected path/content metadata.
They live outside Workspace in private `.studio/git/Selections`. Status and diff
commands run with the object store and Workspace mounted read-only, optional
Git locks disabled, no credentials, no hooks/external diff/textconv, and a fixed
read-command allowlist. Per-read temporary output is isolated and removed. A
frozen preview remains a preview, not a claim that current sources are unchanged.

In v22, `studio_push_project` requires selectionId and a nonempty commitMessage
of at most4000 UTF-8 bytes. There is no default add-all or files argument. The
coordinator verifies the original selection before admitting a new job; the
pinned worker verifies it again before staging and checks the original HEAD
and source hashes around preparation. Changed branch/base/bytes/states require
fresh review. Existing path-specific staging, non-forced single-ref push, remote
confirmation, separate Push permission, workspace lease, pin checks and original
request recovery stay intact. Other files are not selected automatically.

Every original push request remains durable before detailed output. If its
response is missing, read view=job using the pending item's original github.id.
Unknown remains unknown; no second push, automatic reconcile, forced update or
permission expansion is used. Reading old job evidence remains available while
mutation recovery is blocked. Selection IDs cannot be reused across sessions or
original runs.

Host updater profile22 compatibility is prepared by the explicit hash-checked
`scripts/agent-sessions/install-git-inspection-support.py`, followed by normal
release installation. The Git coordinator adopts the installed release only
while idle; active accepted workers keep their immutable release pins.

Only source/contract inspection and static checks are performed. No tests,
fixtures, inference, application-project commit/push or app/VM runs are executed.
Positive end-to-end selection/publication and rejection acceptance remains open
until actual authorized operational evidence exists.
