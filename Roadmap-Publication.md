# Checked roadmap subversion publication (0.8.32)

The versioned project roadmap contract now requires autonomous commit/push after
each actually finished subversion and its passed required checks, when Roadmap
is active, the repository is confirmed and the accepted run permits Push.
There is no additional generic approval step, background publisher or change
to the user's saved global prompt, Workspace/Agents.md or native tool schema.
Existing run rights and explicit user instructions remain authoritative.

New project admissions freeze a small `githubBinding` from Studio's private local
binding receipt, including repository identity, branch and revision. No portable
Workspace metadata or credential is used. The effective runtime composition
states whether publication is enabled or names the missing Push/repository
prerequisite. Only repository ID/name/owner, branch, binding revision and project
ID enter this prompt context; connection/account identifiers and tokens do not.
Roadmap-off, incompatible-profile and skill runs do not receive the active
publication contract. An older frozen run without a confirmed binding cannot
gain a destination from this rule.

`instructions.compose` applies this release's contract before the existing native
start/resume branch, so a new run resuming an older compatible thread receives
the rule without replacing its thread, tool declarations or saved prompt bytes.
Already running release-bound workers keep their original instructions. The
agent Git lease rechecks the complete frozen local binding against the current
binding before admission and effect. Repository/account/branch/revision changes
cannot redirect the accepted run; existing worker, right, pin and lock checks
remain in force. Older accepted runs without the new field retain their prior
host contract.

The agent must inspect/select its own relevant saved source/tests/docs, finish
terminal/development lifecycle work, include the subversion number and meaningful
description, then await the original `studio_push_project` result. It records
original job ID and confirmed commit/remote receipt in roadmap notes before the
next subversion. Implemented/checked and published remain distinct. A confirmed
`nothingToPush` makes no empty commit. Failure/unknown/local-commit-only keeps
publication open and requires original-job reconciliation before another Git
effect. There is no new call-ID retry, force push, bulk historical publication,
implicit tag/release, roadmap cleanup or authority to include unrelated changes.

The tool result now exposes `nothingToPush` explicitly and qualifies original
job identity/state and commit/remote proof before reporting success. A verified
host receipt may report a different descendant remote head after another writer
advanced the branch; the existing host's ancestry proof remains authoritative.
An unqualified/foreign/missing receipt cannot claim publication. Original IDs and
available diagnostic commit/remote fields remain visible for reconciliation.

Four focused groups passed without model inference or user repositories: real
isolated admission/frozen context and repeated start/resume composition with
unchanged saved sources; conditional missing rights/repo/roadmap/profile/skill
cases and original receipt outcomes; actual inherited Git descriptor/worker/
right/frozen-branch enforcement; real local Git commit/noop/lost-response
reconciliation with one commit per intended effect and preserved descriptions.
Network publication was controlled in these isolated cases. Build, frontend/
backend TypeScript, ESLint and Python AST checks passed. No user agent was
started and no user repository was pushed for this qualification.

Evidence: `Research/R4OS/Roadmap-Implementation/0.8.32/` in the development
workspace. Default-on preferences are documented separately in
[Session-Tool-Defaults.md](Session-Tool-Defaults.md).
