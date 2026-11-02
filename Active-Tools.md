# Current tools in existing conversations

Studio 0.9.13 removes session-version tool profiles. The installed
`shared/agent-tools.json` is the declaration and schema source for app projects
and skill workspaces. Workspace kind selects the relevant tools; conversation
age does not restrict them. A new tool requires its catalog entry and real
handler, without a new session generation or a profile allowlist in each service.

Session reads overlay current permission keys onto saved settings. Every saved
true/false choice is retained. Missing newly available keys use the ordinary
defaults, including the trusted local repository requirement for default Push.
This projection does not rewrite saved settings or historical run snapshots.
Settings show the current catalog. Every admitted run captures its catalog hash
and tool names before provider leases are created. A pinned worker verifies that
snapshot against its immutable release. Active calls finish with their original
bindings; the next run or resume uses the installed catalog.

Git, development, notes, Roadmap and Remote Host authorization use the actual
owner, permissions, revision, pins and original worker identity. They do not
reject a session due to a v-number. Current Git publication still requires a
reviewed immutable selection. Original Unknown effects are never replayed.
Actual account/model capabilities and guest/helper readiness remain meaningful
runtime conditions. These are independent of conversation age.

## Native conversation continuity

The qualified Codex 0.163.0 protocol persists dynamic tools in the first
`session_meta` rollout record. Its local generated `ThreadResumeParams` schema
does not expose `dynamicTools`. Studio refreshes that owned metadata before the
native process starts, while holding the original exclusive workspace lease.

The refresh preserves thread ID, timestamps, Goal and usage records, and every
byte after the original metadata record. Before activation it durably saves the
complete original rollout, replacement hashes, unchanged history-tail hash and
original native byte cursors in a private journal. It preserves the original
header width when possible; otherwise it rebases only the corresponding native
projection byte cursors by the exact added width. Cursor updates are transactional
and idempotent. An interrupted metadata update is completed from that original
journal before resume, without a model turn or replaying a tool.

Older built-in OpenAI conversations adopt Studio's existing OpenAI provider alias
to apply its no-replay request policy. Only this known same-account/same-endpoint
alias transition is allowed and journaled with the original provider metadata.
API provider routes, selected accounts and credentials are not redirected.
Claude continues its original native session and receives a newly declared MCP
tool catalog; the bridge is bound to workspace kind instead of profile number.

The privileged update adapter recognizes the unversioned catalog protocol via
the explicit `install-active-tools-support.py` maintenance script. Existing
release compatibility declarations remain readable for original workers and
rollback evidence; they do not select current session tools.

The four existing project conversations already contain the same 46 tool
declarations as the current catalog. They need no rollout rewrite to obtain
this release's tools. Only read-only source/metadata comparison, Python syntax
and import checks, JavaScript syntax, product build/TypeScript and lint were used.
No tests, fixtures, model turns, Git publication of user apps or guest runs were
started for validation. Changed-catalog native refresh is implemented but has
not been exercised against a user conversation as a test.

Protocol background: [official OpenAI App Server documentation](https://learn.chatgpt.com/docs/app-server).
The exact installed 0.163.0 schema and matching local implementation take
precedence over documentation for a different runtime version.
