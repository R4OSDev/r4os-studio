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
