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

Source selection is implemented in 0.9.46. Repository acquisition, activation,
update controls, external MCP execution and complete REA provisioning follow in
the separately planned releases. A configured URL alone is not a ready runtime.
