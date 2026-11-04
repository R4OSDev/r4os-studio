# GitHub skills

Studio stores optional GitHub source configuration separately from published skill
resources. Configure a repository, optional branch/tag/commit and relative skill
directory. The default REA directory is `.agents/skills/reverse-engineer-anything`.
Only the official `morluto/rea` source can select the managed REA runtime recipe.

Configuration uses the existing private skill API, owner lock, optimistic skill
revision and original request ID. Reading a skill or saving a source never
downloads code, starts a process or grants tools/network permissions. Explicit
activation and updates are separate original-ID operations, captured with the
source revision, skill revision and complete draft hash. A pending operation
blocks conflicting source changes. Its status can be read without resubmission;
queued does not mean downloaded or ready. Existing local skills and
immutable published revisions are preserved.

Full repositories and prepared runtimes belong under private
`Data/Skills/<uuid>/Sources/<commit>/` and `Runtimes/<commit>/`. Small instruction
packages continue to use `Workspace/` and immutable `Revisions/`. All installed
REA sources, dependencies, runtimes, analysis programs and caches stay outside
Studio Git, pushes and release archives through the `/Data/` exclusion. Never
force-add them or copy an installation into tracked application directories.

0.9.47 downloads exact Git commits through Studio's existing isolated Git
transport, without checkout filters or hooks. Pinned GitHub submodules are
included. Blob identities, source inventory and executable modes are checked.
POSIX test names are retained losslessly; hostile symlink fixtures are inert
regular blob data with the original Git mode recorded in the manifest.

The source snapshot contains all Git blobs. LFS pointers retain their exact
original content and declare the external object hash/size in the manifest.
They are not reported as materialized binary assets. Activation must resolve
any required skill/runtime asset or name the missing prerequisite; unrelated
third-party test corpora are not automatically downloaded as runtime assets.

Source jobs run in their own private systemd instance, with a complete process
group, original request receipt and limited start/stop authorization. Reading a
receipt does not resubmit a download. Prepared sources are distinct from a
published skill or working runtime. Activation/update controls, external MCP
execution and complete REA provisioning follow in the separately planned
releases. A configured URL or downloaded source alone is not a ready runtime.

0.9.48 validates and publishes ordinary source packages through the existing
skill Save contract. Immutable package identities include the exact source
commit and any managed runtime manifest. Local saves preserve that provenance;
subsequent updates detect local changes rather than replacing them. Identical
updates create no revision, while a different commit keeps its own identity even
when its instruction text is unchanged. A missing runtime recipe fails explicitly
before activation. Publication has a durable private activation journal and
restores its original draft on a confirmed pre-commit failure. A lost receipt is
observed by its original ID; it is never permission to repeat an unknown effect.

The source-only unit permits the private proc mount required by its nested Git
namespace. Its filesystem, device, control-group and kernel-module protections
remain enabled; no web/agent/VM service configuration is replaced.

In Skill Manager → View Skill, expand GitHub source, enter the repository, Ref
and Skill path, then Save source. Public repositories need no GitHub connection;
private ones use an existing connection. Activate prepares the first package;
Update explicitly checks and prepares the selected ref again. Progress, the
confirmed active commit and any failure are shown separately. Cancel source
edits preserves stored settings. Disconnect source preserves instruction files
and ends runtime access for future runs.

The browser retains an original request ID across reload and observes that
request after a lost response. Check status / refresh access renews access and
reads current state without starting preparation. Concurrent edits report a
conflict and preserve entered fields. Session Settings continues to select each
skill by its existing UUID; tool permissions remain independent.
