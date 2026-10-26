# R4OS Studio · App





## Native SYSUPD preflight and text adapter (0.4.14)

POST /api/projects/<uuid>/update-packages/probes accepts requestId, projectRevision and packageArtifactId. The durable VM job uses the explicitly assigned, already running VM, existing private loopback forwarding, pinned SSH/SFTP clients, fixed login policy and VM-bound host-key trust. It reserves the shared VM lease and binds VM UUID/configuration, system generation, base-image hash, QEMU invocation and guest boot before fixed VER, SYSUPD STATUS, TYPE VERSION.R4S and TYPE MODULES.JSON calls. It cannot start a VM, upload, install, commit or reboot.

SYSUPD STATUS can materialize UPDATE/INBOX/STAGED. The adapter requires confirmed success and dirs=ok, captures both journal and batch state, then closes the observation interval with another matching status. Idle and terminal journal cleanup/rolled_back or batch installed/rolled-back preserve history and permit a future fresh upload check. Foreign, failed or recoverable active states block new work; owned active states require recovery. No journal is adopted/deleted, and source=- alone proves no ownership. The lease coordinates Studio actors; STATUS is a snapshot and supplies no native writer lock or expected-batch compare-and-execute guarantee.

The central parser handles native STATUS plus VERIFY/APPLY/STAGE/COMMIT/RESUME/RESUME-BATCH/ABORT-BATCH/ROLLBACK-LAST result lines. Known field boundaries preserve spaces in Pending restart and other display states; lowercase status phases remain distinct. IDs/counters stay unsigned 64-bit decimal strings. STAGE can return an effective APPLY; terminal RESUME-BATCH can omit batch identity. Native failures, incompatibility, interruption, contradictory exit/result pairs, unknown formats and incomplete channels do not authorize subsequent mutation. Successful command execution and reported rolled-back/installed states do not themselves confirm package installation; later inventory/byte evidence remains required. SYSUPD has no JSON or VERIFY-BATCH command.

SSH exec has an opt-in complete receipt retaining bounded stdout, stderr, byte counts, real exit status, timeout/truncation and transport uncertainty. Its existing default output/exception contract for app runs is unchanged. Channel quota 128 KiB, combined observation 256 KiB, probe deadline 180 seconds. Original captures and source-bound adapter hash remain in the job/private evidence.

Actual Full 0.87.14 revealed a guest SSHD console-hook limit: TYPE MODULES.JSON lost 366 bytes and exited 3, despite the client receiving its stream completely. The full inventory is therefore also read twice through the existing SFTP client using only the fixed readonly metadata path. Matching complete sizes/SHA-256 and parsed entries are required; TYPE's original failure remains recorded. Only the source-confirmed exit 3 console-loss diagnostic allows that fallback; other command failures or mismatched reads block the workflow. The generic deployment-path policy is unchanged; no arbitrary read path, new guest script or general shell endpoint is exposed.

The observed installed release from VERSION.R4S, active kernel from VER and immutable base-image identity remain separate. New status data never changes images, project pins, defaults, host-key trust or old deployment receipts. Sources/hashes and quotas are in shared/r4os/sysupd-adapter.json; current source review corresponds to the tested engine, without an image/SDK revision allowlist.

Validated with actual private SSH/native STATUS, release 0.87.14, kernel 0.1.384 and 110 stable SFTP inventory entries in a clearly named own VM from the already imported Full image. Thirty-six development Python cases including twelve parser/transport/preflight cases, unprivileged checks, backend session/CSRF/fixed-input tests, build/TypeScript/lint and installed VM-job evidence are under Research/R4OS/Roadmap-Implementation/0.4.14/. Productive VMs/defaults remain unchanged. The own project/package/VM are retained temporarily for the subsequent transfer/installation integration.


## Immutable native package jobs (0.4.13)

POST /api/projects/<uuid>/update-packages/builds accepts only requestId, projectRevision, planId and planSha256. It starts one durable package job through the existing private development coordinator and bounded non-VM worker. GET /development/jobs/<job-id> reports its original state/output; GET /update-packages/artifacts/<package-id> verifies and returns the resulting immutable package receipt. Repeating the same accepted request returns its original job, including after a lost response or a later default change. An unconfirmed result remains unknown and is never rebuilt automatically.

Admission freezes the complete plan, project/source/manifest/artifact/native-inspector/Packer hashes and a private exact executable binding. The active qualified Packer must match the plan at admission; select that profile or create a new plan if the default changed. Accepted jobs retain their bound program independently of later defaults. Packaging never downloads/activates a tool, rebuilds the app, reads workspace changes or opens VM access.

The worker copies and hashes confirmed artifact bytes and the exact qualified executable into private job storage. A network-isolated namespace exposes only readonly inputs/Packer, host runtime files and its own writable output directory. The native process is invoked through structured argv: SOURCE|TARGET|KIND and the exact five-field requirements each remain a single value. Title text cannot become a shell command. Both stdout and stderr are bounded and labelled, with separate byte counts; success requires the actual exit code 0, complete R4U2 bytes and final source/program/output rechecks. Limits remain two host jobs/one per project, 60 seconds, 128 MiB package bytes and 2 MiB diagnostics; existing build limits are unchanged.

Completed bytes and native provenance publish atomically under the selected project's Development/UpdatePackages/<uuid>/, outside the editable Workspace. Additive update_artifacts rows and the final job state commit together. No existing package is overwritten. Stop, malformed inputs, changed files, process errors, oversized/truncated output or lost confirmation preserve diagnostics/partial private work and never produce a confirmed package. A private publication record is retained if the final database confirmation is missing; unknown is preserved until evidence supports an explicit reconciliation. Successful disposable package work is removed after artifact verification.

Explicit one-time host maintenance: python3 App/scripts/project-development/install-package-support.py as root. It changes only the known dispatcher decision so build/package use the existing non-VM unit, records its root-owned hash and leaves bootstrap, config, unit definitions, old workers and VMs in place. Unknown customized dispatchers are preserved for review. Normal web updates never execute this root installer. Fresh setup also uses the extended release-owned dispatcher. A capability gate blocks new package admission until the installed dispatcher and worker support are qualified.

Validated with actual unprivileged native packaging of the prior C build, successful stderr output and immutable 9472-byte R4U2 result. Twenty-four development Python cases, seven unprivileged package cases, backend identity/session/CSRF/path checks, build/TypeScript/lint, targeted host-preservation checks and installed bounded-worker package/replay/read proof are recorded under Research/R4OS/Roadmap-Implementation/0.4.13/. No new dependency or native agent profile is introduced. Guest preflight/transfer/installation and agent tools remain subsequent 0.4.14–0.4.20 work.


## Artifact-bound update package plans (0.4.12)

The private development coordinator exposes project-scoped package proposals at /api/projects/<uuid>/update-packages: GET options/configuration, POST plans, GET plans/<plan-id> and POST batch-preview. A proposal binds confirmed immutable build artifact IDs, captured module.R4MF SHA-256, source/build-proof/native-inspector hashes, project pins, exact selected Packer profile, package ID/version, explicit target release and bounded UTF-8 title/description. It has its own configuration revision, request identity and content hash. Repeating an accepted request returns its original plan; stale or changed requests preserve existing settings/plans.

New builds can record native update identity through a small Studio adapter calling the pinned SDK's original r4u_artifact.inspect and manifest install-mode/priority functions. It runs in the existing credential-free build namespace and compares kind/name/embedded version to the SDK catalogue entry from that build. Targets come from that same catalogue/captured manifest, mapped to C: without substituting Exchange paths. This capability is optional for ordinary builds; older artifacts or SDKs without a qualified identity need a new compatible build for update packaging. Build results and old artifact formats remain readable.

Current eligible inputs are actual confirmed versioned R4X/service/R4L/R4D/R4P artifacts. Other formats, Kernel, unversioned or companion payloads cannot be invented from workspace files: they require a confirmed native artifact adapter/receipt and their concrete recovery requirements. This release accepts no arbitrary source paths, output targets, activation overrides or host executables. It does not infer guest component versions from SDK/Contract pins or API import names. Requirements are explicit concrete KIND|NAME|TARGET|MIN_VERSION|STATE values with exactly five fields; active is kernel-only.

Plans reject foreign drives, managed VERSION.R4S/MODULES.JSON, traversal, conflicting targets and mismatched native identities. Limits are 32 payloads/requirements, conservative 32-KiB manifest upper bound, native u32 complete-container ceiling and a separate 128-MiB Studio container ceiling; existing development quotas are unchanged. Batch preview checks 1–16 packages, aggregate 32 components/requirements, one target release and distinct targets. Native build/guest verification remains required; no JSON or VERIFY-BATCH guest API is assumed. An offline plan requires an explicit target release; a future VM preflight can offer a freshly observed release.

All plan details are returned before packaging or guest mutation. This release adds the backend/contracts; project settings and job controls integrate them in 0.4.20. Package builds follow in 0.4.13. State uses additive schema-1 tables in the selected project's Development.sqlite. No global reset or data migration, host installer, source download during planning, VM effect or automatic action on update is introduced.

Validation covers native SDK metadata from a real isolated C build, exact manifest-to-C: target mapping, installed HTTP plan/replay/read/batch preview, tampered input/native metadata, wrong-owner artifacts, revisions, strict requirements and quotas. Seventeen development Python cases including five plan cases, five unprivileged plan cases, backend session/CSRF/path-boundary checks, build/TypeScript and lint passed. Evidence and cleanup are under Research/R4OS/Roadmap-Implementation/0.4.12/.


## Qualified native R4UPack (0.4.11)

System → Updates → Tools → **R4UPack** inventories the separately installed native packer, checks the fixed qualified profile, builds it on explicit request and selects it independently. Building never activates it. The displayed 0.64.18 is the Distribution source package version; the complete profile ID, Distribution/SDK source revisions, compiler and binary SHA-256 identify this tool. Native --version supplies package metadata and is never used to query the executable.

The minimal recipe compiles unchanged Distribution ecbe622b5d26244fad449c72cb483936798e172e Tools/R4UPack/src/main.zig with four checked SDK 51ed03d813d9baeab630746f1d1bbc46c2d2a1e6 modules, existing Zig 0.16.0 and fixed ReleaseSafe/x86_64-linux-gnu/strip arguments. Sources and licenses, compiler archive/binary hashes, source-file hashes and expected resulting binary 536b341395421a5626c03e4c3165fd58b3b347042dd515037663554afa6de8f1 are pinned in shared/r4os/r4upack-profile.json. No complete workspace, Kernel, image sources, Libraries or PowerShell are required.

Explicit local setup as data owner: runuser -u r4os-studio -- python3 App/scripts/setup-r4upack.py from the workspace root. An administrator can provide --source-dir with repository/path files for offline setup; all files must match the fixed profile. Existing Zig must already match; setup does not download/select a compiler. The existing unprivileged component service can build the same profile through its bounded interface; the web service receives no shell. HTTPS downloads are fixed to the pinned official files and checked before compilation. No packaging job downloads or activates tools.

Profiles publish atomically under Data/R4OS/Toolchains/R4UPack/<profile-id>/, retaining source closure, licenses, help diagnostics and qualification metadata. Explicit selection is private Data/R4OS/Profiles/r4upack.json, separate from unchanged SDK/Contract/compiler/defaults in versions.json. The components/r4upack.pin helper resolves and verifies exact path/hash/profile at future job admission. An administrator-only external.r4upack binding in the existing components config may provide exactly {binary,directory,sha256}; the binary and full retained qualification directory must match the same checked profile. This cannot be supplied in a browser/agent request. Symlinks, hardlinks, altered binaries/sources/licenses and unsupported selections are rejected with existing files retained.

Qualification: two actual unprivileged builds at different paths produced the identical expected binary; native help/argument checks prove --version is an input, and all retained files verify. Eleven component/Packer Python cases, two backend boundary checks, build/TypeScript/lint and isolated browser navigation/explicit selection/persistence at 1440/320 px passed. Installed host inventory/selection evidence is under Research/R4OS/Roadmap-Implementation/0.4.11/. Normal Studio update adoption suffices; existing bootstrap, old releases, projects, SDK defaults and VMs are preserved. Package planning/building and guest installation follow in 0.4.12–0.4.20.


## Isolated skill scripts (0.4.10)

Selection-aware script-capable runs expose each frozen enabled package read-only at `/skills/<uuid>` inside the existing file/terminal namespace. The catalogue supplies that terminalPath alongside the unchanged virtual file-broker path. Relative scripts/references/assets resolve within the same frozen revision; requested outputs stay in the selected Workspace/private run cache. No skill sources are copied into projects, no workspace markers are created, and old accepted configs without script scope do not gain mounts.

Execution uses only the existing `exec_command`, `write_stdin` and `terminate_process` calls and their frozen permissions. The web service gains no shell or permission. Available host interpreters and existing pinned project components are reused; missing interpreters/dependencies return actual failures, without installation or network/credential/VM/GitHub grants. Opening, importing, validating and saving never execute a script. Existing handles/time/output/resource bounds, terminal exit/signal/reason data and owned-process cleanup remain in force. An accepted Stop during preparation closes process admission before launch.

New API runs require coordinator script capability and explicitly request the script scope; the selected immutable worker release must support it. Existing native profiles/tool names/root enums and update contracts are unchanged. Accepted old workers continue with their release/snapshot/scope across Studio updates; compatible coordinator adoption occurs when idle. The script namespace mounts only frozen active revisions and the already authorized selected workspace/cache/components; global catalog/settings, other drafts/projects, provider secrets and VM state remain absent.

Validated with actual unprivileged script namespaces: Python/reference/binary-asset use and selected outputs, readonly write rejection, live old-revision binding while a global Save creates a new revision, next-run revision change, actual exit7/import failure/missing interpreter/timeout statuses, process cleanup, disabled exec, removed skill mounts and retained legacy scope. Project/skill API regressions, build/TypeScript/lint and existing agent/runtime checks passed. Tagged-update evidence with an old0.4.9 worker and installed native script workflow in both contexts is recorded under `Research/R4OS/Roadmap-Implementation/0.4.10/` outside the public repository. No additional dependency, host support installer or data migration is required.


## Global skills per session (0.4.9)

Session settings → **Skills** is available in project and Skill Manager sessions. Missing choices mean enabled, including newly published skills in existing sessions. Name, availability and an on/off switch are shown for every Studio skill; drafts can be excluded before publication. Save/Cancel, conflicts, idle restrictions and the session revision apply to these choices. A settings reload also refreshes the surrounding session so subsequent actions use the current revision.

Only false exceptions are stored in new private `Data/Skills/SessionSettings.sqlite` (schema1,0600), keyed by owner type/owner UUID/session UUID. Reads of unset choices write nothing. An explicit changed Save initializes this auxiliary store, then attaches it to the existing owner session database and commits exceptions and the existing session revision atomically using full-synchronous SQLite rollback journals. Existing main session/catalog schemas are unchanged; older releases ignore/preserve the auxiliary data even when saving their basic settings. Unsupported journals or corrupt settings fail while preserving bytes. No new host write path, dependency or bootstrap migration is needed.

Every selection-aware run freezes the current enabled published metadata, catalogue/display revision, active revision/tree hash, manifest hash and complete file hashes/references. Global Save/rename and session switches affect later runs. Drafts have a visible unavailable notice; altered/unavailable published snapshots block admission until repaired or excluded. Limits are **64 enabled published skills,96KiB metadata catalogue and128MiB combined resources**; exceeding them reports a concrete error. Resources stay in retained immutable revisions, without project/global skill copies or workspace changes.

The baseInstructions catalogue contains name/description and a virtual path such as `__studio_skills__/<uuid>/SKILL.md` under the existing `workspace` root. A collision-free bounded alias is chosen without creating files. Full instructions/references are read only on demand through the existing permitted file calls in a separate readonly namespace containing only frozen selected revisions. Existing native tool names/profiles/root enums remain unchanged, including legacy project v1–v4 and skill v1/v2. Virtual writes/patches are rejected before effects; disabled or superseded resource receipts cannot provide a new response outside the current selection. Native/plugin/bundled/host skill discovery stays disabled. Script terminal mounts follow in0.4.10.

Skills supplement user/base/project/author instructions and grant no extra tool/network/credential/VM/GitHub rights. Disabling removes the next-run catalogue and resource access. **Previously read content remains in the native conversation history**; native threads/history are retained. File/terminal permissions remain independent. New API runs require coordinator global-skill capability; compatible idle adoption uses the existing coordinator release mechanism, while already accepted old workers/runs keep their original scope and release.

Validated: default/new skill behavior, independent typed owners (including same UUIDs), atomic idle/revision exceptions, older settings preservation, frozen revisions/rename, bounds/corruption, unchanged native declarations and same-thread catalogue refresh; actual unprivileged readonly resource access without SDK, write/traversal/disabled/resource-receipt denial and read permissions. Backend project/skill/prompt/library regressions, build/TypeScript/lint, and browser1440/320 in both owner contexts cover save/cancel/persistence, draft availability, keyboard controls, conflicts/reload and no inference on open/settings. Actual native resource selection and cleanup evidence: `Research/R4OS/Roadmap-Implementation/0.4.9/` outside the public repository.


## Skill session navigation and chat (0.4.8)

Tools → Skill Manager → selected skill has a fixed upper block **+ Session**, **View Skill**, then a separately scrollable list of that skill's saved sessions. Session creation accepts a user name and existing provider/model/reasoning/Fast Mode without an inference request for naming. Selection and `#tools/skills/<uuid>/sessions/<uuid>` links survive reload and browser Back/Forward. Dirty/busy guards cover editor changes, session settings, dialogs and navigation; an active run continues across tabs and remains stoppable when returning.

The existing chat/composer/history/SSE/Stop/reconnect components now use a typed project/skill HTTP context. Skill requests and event streams use only `/api/skills`, its own browser/CSRF scope and owner IDs; project behavior keeps its existing default context. Native VM/development image endpoints are unavailable in the skill transcript. Browser pending creation/run/draft keys are separate for the skill scope. Run and confirmed Save events refresh the skill catalog, while an editor's local text remains untouched and stale writes retain their text on conflict. Existing actual native resume/author publication proofs from0.4.5/7 remain applicable; this release adds the browser interface to those unchanged APIs.

Session settings expose name, provider, model, reasoning, Fast Mode and the current author's actual tool permissions, with one revision-protected idle Save. Skill sessions have Files/Terminal/Skills groups; project-only Build/VM groups are absent. Composer model controls remain available. Global skill selection follows in0.4.9. New-session controls reuse the existing model catalog and default-enabled author permissions. Skill creation and Save now use the established getRandomValues-based UUID helper so HTTP LAN origins work without crypto.randomUUID.

Validated: build/TypeScript/lint and two targeted project/skill backend regressions. Isolated browser1440/320 exercises session creation/settings, scoped API/SSE, forced reconnect without new inference, a confirmed revision card, disabled rights, active-run tab return/Stop, ownership, safe Markdown, deep links/reload/Back/Forward and a second editor's retained local draft/conflict. Browser run/SSE results are explicitly simulated in a private fixture; real native runtime/publication were independently verified in0.4.5/7. The test disables secure-context randomUUID and retains only the app's existing provider-list bootstrap. No new application dependency or host permission is needed. Evidence and cleanup: `Research/R4OS/Roadmap-Implementation/0.4.8/` outside the public repository.


## Bound skill author tools (0.4.7)

New Skill Manager sessions use `studio-skill-tools-v2`: the nine general workspace tools plus **Validate skill** and **Save skill**. Permissions default to enabled, remain editable only while idle, freeze per run and are checked before every call. Existing skill v1 and project v1–v4 sessions keep their original profiles and native threads. The special prompt describes draft-only requests, requested global Save, validation/resource fixes, honest confirmed results and no automatic script execution.

`studio_validate_skill` checks the complete current selected draft and returns its catalog revision, full draftHash, relative files and bounded diagnostics. An optional expectedDraftHash rejects a changed draft. `studio_save_skill` requires that exact revision/hash and uses the existing complete immutable snapshot/atomic active-pointer publication. Only the selected skill can be saved. Durable request IDs derive from run/call identity; confirmed calls replay their original receipt, changed arguments conflict, unknown effects never repeat. Invalid drafts preserve the current active revision. Tool cards retain relative files, validation issues and confirmed active revision/SHA-256; full chat navigation follows in0.4.8.

A fixed author broker runs outside the model/tool namespace. It receives only the selected owner/session/run, operation, bounded arguments and the worker's already-held workspace lease FD. It checks the lock inode, run state/owner/revision/permission and parent worker PID/birth before validation/publication, and again before publication effects. The FD never enters Codex, terminal tools or the Node YAML validator. The broker grants no arbitrary path, credential, VM, network or script execution capability. Author calls serialize with file/terminal admission and wait for existing terminal processes to finish; manual editing stays blocked for the active run. Loss of the publication response yields unknown while preserving snapshots/receipts and stopping follow-up effects.

Explicit local host qualification: `python3 App/scripts/agent-sessions/install-author-support.py` before tagged installation, then `--adopt` with an idle coordinator after installation. Only the known updater compatibility is extended; current services/configuration/write paths and running old workers/VMs are preserved. Older compatible rollback targets remain accepted. Custom Skill Manager prompts are retained; shipped defaults describe the current available calls conditionally.

Validated with real fixed broker execution as an unprivileged user, owner/lease/permission/Stop bounds, invalid and stale drafts, publication/receipt replay, unknown response recovery, original thread/profile retention, project/skill API regressions, update compatibility, build/TypeScript/lint. Installed native author publication and cleanup evidence are recorded outside the public repository in `Research/R4OS/Roadmap-Implementation/0.4.7/`. No new application dependency or bootstrap/data migration is introduced.


## Skill Manager Prompt (0.4.6)

System → Settings → **Skill Manager Prompt** edits the separate author instructions through the existing prompt editor, with Save changes, Cancel, Reset to default, dirty-navigation protection and conflict-preserving reload. The scope text identifies Skill Manager sessions. The existing System Prompt applies to project sessions, and its text/reset remain independent.

A separate private `Projects/.studio/SkillManagerSettings.sqlite` setting (schema1,0600) stores the optional override and revision. The existing `Settings.sqlite` project prompt is preserved without migration. Both fixed prompt endpoints expose text/default/revision/isDefault/SHA-256, use existing Settings session/CSRF/host/origin checks, enforce nonempty UTF-8 up to32KiB without control characters, and retain identical-retry/conflict semantics. Corrupt storage fails while preserving its bytes and does not affect the other prompt. Custom text survives updates; an unset override follows the versioned shipped default. No additional dependency or host permission is required.

Skill run admission freezes the effective author text, revision and SHA-256. The worker verifies the checksum and applies that snapshot through qualified native `baseInstructions` on thread/start and thread/resume. Accepted/running runs keep their original prompt; later runs use the current saved text in the same native thread, without rewriting history or starting inference on open. The existing project instruction flow is retained. The default describes trigger clarification, concise SKILL.md, optional resources/scripts, validation/publication boundaries and honest results; bound author tools follow in0.4.7.

Validation: four targeted backend cases for both prompt settings and skill sessions, nine agent tests (one root-only namespace skip), frozen-prompt/current-thread RPC assertions, build/TypeScript/lint and isolated browser1440/320 for persistence, save/cancel/reset, leave guard, concurrent conflicts/reload and separate project prompt. Own browser data is removed afterwards; production prompts/accounts/projects/VMs/pins remain unchanged. Evidence outside the public repository: `Research/R4OS/Roadmap-Implementation/0.4.6/`.


## 0.4.5: Independent Skill Manager sessions

Skill sessions use a typed `owner` (`project` or `skill`) and a separate Sessions.sqlite/native Codex history under the selected skill UUID. No placeholder project, app manifest, SDK, compiler profile or VM assignment is needed. The legacy private SQLite column name remains compatible; public skill DTOs contain `skillId` and no `projectId`. Existing project UUIDs, tool profiles v1–v4, native thread IDs and histories remain valid without migration.

`/api/skills/:id/sessions` provides options, creation, list/detail, revision-protected settings, cursor history/SSE, explicit run submission and Stop, using the private Skills browser session/CSRF/host/origin checks. The original provider Codex home and cached model catalog are reused without credential copies. `studio-skill-tools-v1` exposes only the nine general file/terminal calls, with the selected workspace as its sole file root. Its separate frozen Skill Manager instructions do not inherit project/global app instructions. Prompt editing follows in 0.4.6; author validation/publication tools and the full session UI follow in 0.4.7–8.

The shared coordinator admits at most one run per owner workspace and two agent runs in total across Projects and Tools. Worker manifests pin both the owner and immutable release. Skill authors hold the same OS workspace lock as manual editors; queued/busy runs also prevent manual writes/publication. Durable tool receipts, user Stop, unknown outcomes without replay, native thread resume and non-inference recovery are shared with projects. The author tool namespace mounts only the selected draft and private run caches; SDKs, other owners, session storage, credentials, VMs and network are unavailable. Native authentication remains in the original separate credential namespace.

Explicit host maintenance is `python3 App/scripts/agent-sessions/install-skill-support.py` before publishing/installing the release, then the same command with `--adopt` after installation while agent runs are idle. It qualifies the additive update contract and dispatcher, adds Skills write paths only to the existing coordinator/worker units, and preserves bootstrap/configuration, running old workers and all VMs. Known prior host file hashes are required; downloaded privileged installers are never run. Existing rollback releases remain accepted and preserve skill data; older releases cannot start skill sessions.

Validation: targeted backend API/ownership/security/history/SSE tests; shared admission, stop, recovery and native continuity tests; actual unprivileged author file/terminal namespace checks without SDK; project regression tests and update compatibility checks; build/TypeScript/lint. Stale preexisting project fixtures (tool count and current instruction/profile contract) were first reproduced on unchanged HEAD and then aligned. Release evidence, installed runtime verification and cleanup are recorded under `Research/R4OS/Roadmap-Implementation/0.4.5/` outside the public repository.


## Tools and manual skill editing (0.4.4)

The header order is **System, Projects, Tools**. Tools has three equal navigation columns: TOOLS → Skill Manager; SKILLS → + New Skill and saved skills; selected-skill Views → fixed + Session and View Skill. + Session is disabled until the planned session UI is connected in0.4.8. Existing System → Updates → Tools remains a separate navigation item. Skill selection survives reload through #tools/skills/<uuid>.

View Skill shows the draft package with an editable display name, file selector inside the main area, existing CodeMirror editor, safe Markdown preview, Save and Cancel edits. Optional scripts/resources can be created, edited, renamed, removed, uploaded/replaced and downloaded. Executable flags are explicit for script files. Binary assets are downloaded/replaced rather than interpreted as source text. Text editor limit is524288 characters; larger files remain available for download/replacement under the package limits. Package resource links open the corresponding file inside the main area. Markdown HTML is skipped and remote images never auto-fetch. Viewing/saving never executes scripts.

File operations explicitly update the stored draft; **Save skill** writes edited text using expected hashes, checks the full skill/package revision and activates only a valid complete snapshot. Invalid saves retain the draft and previous valid global revision. Cancel edits restores unsaved text/name/mode changes; it does not erase previously stored draft files. External file conflicts preserve local text for a deliberate Reload. Dirty/busy guards cover header/skill navigation, dialogs and reload. No fourth sidebar, model request or project/SDK requirement is introduced.

Validated: build/TypeScript/lint and isolated browser at1440/320 pixels, including narrow initial header, equal columns, draft creation/validation/save, script editing/executable flag/rename/confirmed removal, binary upload/download, safe preview, cancel/leave protection, stale-file conflict/readback, display renaming without identity changes and route/file persistence. Fixtures remain confined to the isolated QA directory and are removed after validation. Skill runtime/session application follows in0.4.5–0.4.10; existing projects, providers, credentials, VMs and component defaults are preserved.

## Global skill library foundation (0.4.3)

The host API `/api/skills` now manages a Studio-wide skill catalog independently of projects, SDKs, compilers and VMs. The Tools tab and manual browser editor follow in 0.4.4; session activation/inference integration follows in 0.4.5–0.4.10. No arbitrary host/Codex skills are imported or enabled by this release.

Private storage is `Data/Skills/Skills.sqlite`, beside the configured provider storage. Each immutable UUID owns `Workspace/` (editable draft), `Revisions/<tree-hash>/Workspace/` (complete immutable package) and `Sessions/` (reserved for its later conversation history). Display name and SKILL.md format name can change independently of identity. Reads and mutations use a separate HttpOnly/SameSite/CSRF/Host/Origin scope, bounded fixed Python operations and OS-released per-skill write locks. No compiler, shell or model execution occurs while managing files.

`SKILL.md` uses YAML frontmatter with explicit name/description and Markdown instructions. Optional scripts/, references/, assets/ and agents/ files are supported. The already available **js-yaml 4.3.2** is now a direct pinned dependency for real YAML parsing (JSON schema; no executable tags), through a fixed bounded Node validator invoked by the Python store. Metadata such as allowed-tools does not install dependencies or grant runtime rights. Name uses lowercase words/digits and single hyphens, at most64 characters; description is nonempty and at most1024 characters. Instructions are UTF-8 up to64KiB; text scripts/references must be UTF-8, binary assets use base64 at the API boundary. Limits: 256 skills, 128 files/512 entries and8MiB per package,1MiB per file. Relative canonical paths, regular single-link files, case-distinct conflicts, links/special files and local Markdown resource references are checked. Resources are not fetched or executed.

File edits check expected SHA-256 and preserve invalid drafts for editing. A normal Save checks the catalog revision and complete tree hash, validates a complete package, writes/fsyncs a complete snapshot, then atomically advances the SQLite active pointer. Invalid saves retain both the working draft and last valid revision. Request receipts make a repeated completed Save return its original result; conflicts cannot replace newer data. All historical snapshots are retained for later accepted runs. Unknown/corrupt catalogs and altered snapshots fail while preserving data; no automatic schema migration/reset occurs. A rollback to an earlier Studio release leaves this additive private store intact.

Explicit local setup: `python3 App/scripts/skills/install.py` from the workspace root. It creates only the private Skills directory (r4os-studio,0700) and the web-service ReadWritePaths drop-in; the next regular update applies it. Existing agent workers, provider credentials, projects, VMs, component pins and bootstrap remain intact. Data remains ignored by Git.

Validated: targeted API/storage cases for draft/save/persistence, complete revisions and invalid-draft retention, display/format renaming, hashes/concurrency, bounds, traversal/links, CSRF/Host/Origin and corrupt storage, plus existing GitHub/system-prompt regressions; build/TypeScript/lint and Python syntax. A real unprivileged isolated r4os-studio helper run created, edited, validated and saved a skill without SDK/compiler/project/VM context, then removed its fixture. No script execution, inference or production skill was used.

## GitHub connection tests (0.4.2)

**Test connection** is available for an unsaved token and for a saved connection. Draft tests do not save credentials. The host sends one authenticated read-only `GET https://api.github.com/user`, using the documented `2026-03-10` API version, recommended JSON Accept header and TLS verification. Redirects are not followed, the total request deadline is ten seconds, response data is bounded to 64 KiB and at most four tests run concurrently. There are no Git/shell commands, repository mutations, background polls or credential imports. Source: [GitHub authenticated user endpoint](https://docs.github.com/en/rest/users/users#get-the-authenticated-user).

Only status, checked time and a successful public login/user ID are projected. Authentication rejection, restrictions, rate limiting, network/TLS failure, timeout, server failure and invalid/oversized responses receive bounded English feedback; raw responses/headers are neither stored nor displayed. Success confirms identity at the test time and does not establish repository, organization or push permissions. Existing 0.4.1 catalogs remain readable without rewriting credentials or inferring prior tests.

Saved results bind the connection UUID, token generation and latest test attempt. Token replacement clears prior results; rename retains the token-bound result. Responses after replacement/removal or a newer test are discarded. Draft edits clear their displayed test result. Existing Settings session/CSRF/Host/Origin checks protect both test paths.

Validated with six targeted backend cases (adapter failures/limits/timeouts, draft non-persistence, token/attempt races, legacy catalog compatibility, storage/security and system-prompt regression), build/TypeScript/lint and isolated browser checks at 1440/320 px. The user explicitly accepted isolated tests without a separate real GitHub test account; no successful live authentication is claimed and the private push token was not accessed. Fixtures were removed. No new application dependency or host permission change is needed beyond 0.4.1.

## GitHub connections (0.4.1)

System → Settings → GitHub manages named personal-access-token connections. Views starts with **+ Connection**, followed by connection names. Add, rename, explicitly replace a masked token, cancel changes and confirm removal in the browser. Unsaved edits are guarded during navigation/reload. Connection tests follow in 0.4.2; this release performs no GitHub requests or repository actions.

The backend stores a private atomic catalog under `Data/GitHub/connections.json`, next to the configured provider directory (`STUDIO_DATA_DIR` identifies the provider directory itself). Directory/file modes are 0700/0600. Only explicitly projected metadata, revision and token-present status reach the browser. Tokens are never returned or copied into project workspaces, agent runs, VM data, logs or public source. All of Data remains ignored by Git. Classic and fine-grained tokens can be stored; storage does not prove validity or repository permissions. Master refers to the installation's existing trusted administrator; no new user-role system is introduced.

The API `/api/github` uses separate HttpOnly/SameSite browser ownership and CSRF tokens through the shared Settings security model, plus allowed Host/Origin checks. UUIDs distinguish duplicate names/accounts; writes check revisions against fresh disk data. Exclusive create locks protect simultaneous processes, atomic rename/fsync publishes one private snapshot, and create/update/delete retries preserve their intended result. A persistent `.write.lock` after an interrupted writer fails closed: stop Studio and verify no writer is active before host maintenance removes that lock. Corrupt storage is preserved and reported, never reinitialized. No public token-read endpoint exists.

For this managed host, run the explicit installer `python3 App/scripts/install-github-support.py` from the workspace root. It prepares only Data/GitHub and a service ReadWritePaths drop-in, retaining the update bootstrap, provider credentials, projects, VMs and pins. The next regular Studio release installation applies it; downloaded updates never execute root installers. No new application dependency is required.

Validated: focused API/storage tests covering secret redaction, CSRF/Host/Origin, invalid input, duplicate names, revision conflicts, retries, token replacement/removal, permissions, restart/corruption and independent server instances; existing system-prompt regression; build/TypeScript and lint. Isolated browser checks at 1440/320 px cover create/replace/cancel, dirty navigation, reload, conflict preservation/reconciliation and confirmed removal with no external network calls or production credentials.

Version 0.3.70 zeigt referenzierte Screenshots direkt in Agentenantworten. Authentifizierte Projekt-/Session-Belege, Vergrößerung mit Fit/Actual size und Original-PNG-Download verwenden dieselben Bilddaten. Reload und paginierte Historie bleiben erhalten; vorhandene Tools und Aufnahmeberechtigungen unverändert.

Version 0.3.69 wartet bei Builds im Harness und reduziert unveränderte Gast-/Zustandsdaten. Adaptive Beobachtung wird bei Stop oder Aktionen geweckt; kritische Quittungen, Watchdogfristen und frische Screenshot-/Eingabeprüfungen bleiben erhalten.

Version 0.3.68 erweitert die Agent-Suche auf reguläre Einzeldateien und Verzeichnisse. Keine Linkverfolgung; begrenzte UTF-8-/Dateinamen-Suche mit präzisen Fehlern, stabilen relativen Treffern und sichtbaren Auslassungen.

Version 0.3.67 korrigiert den VM-/Deployvertrag: VM-Start wartet separat bis SSH/VER, Deploy startet weder VM noch App. Früher Preflight verhindert Helperarbeit bei fehlender VM-/Workerbereitschaft; aktualisierte Laufhinweise erreichen auch bestehende Threads.

Version 0.3.66 ergänzt einen ausdrücklich quittierten Prüfabschluss. Nach erfüllten Kriterien beendet Studio nur den eigenen Testprozess und bestätigt Cleanup; echte Timeouts, fehlende Exitbelege und unbekannte Wirkungen bleiben unterscheidbar. Neue Sessions verwenden das additive Toolprofil v4, bestehende Threads bleiben erhalten.

Version 0.3.65 korrigiert SDK Check for Updates: veröffentlichte stabile SDK-Releases statt unveröffentlichter main-Paketversionen. Fehlende ältere Paketmetadaten werden konkret erklärt; Standards und Projektpins bleiben erhalten.

## SDK update discovery (0.3.65)

SDK Check for Updates lists official stable GitHub releases and resolves their
exact tags, including annotated tags. SDK source package versions from main are
not release identities: they can exist without SDK-Release.json or downloadable
package sets. The SDK catalog does not fetch main; missing source objects are
fetched only from the selected release tags. Latest/older pagination stays
bounded, and a package version must match its release tag.

The release's manifest asset is checked before fetching it. Local SDK revisions
without a published release and older releases without SDK-Release.json keep
clear status reasons while their installations and project pins are preserved.
Older manifests without Libraries cannot activate a combined component set.
Cached valid manifests remain usable; unexpected manifest 404 responses get a
specific metadata message. Transport failures and invalid metadata remain
visible. SDK/Contract/Libraries identities, archive hashes, contents and atomic
selection rules are unchanged. No fallback dependencies or automatic default
changes are introduced; this is release discovery, not a Studio revision list.

Syntax, Studio build/TypeScript and lint are the static verification scope.
No test suites, VM/app runs or component downloads/default changes are required.
The installed SDK update check is verified through its normal endpoint.


Version 0.3.64 bindet den nativen DESKRUN-0.1.1-Desktopstart über SSH an. Originalkennung und u64-Quittungen bleiben exakt erhalten; Timeout führt nur zu STATUS, niemals zu einem zweiten Start.

## Native desktop launch through SSH (0.3.64)

Studio integrates the public DESKRUN 0.1.1 JSON contract, announced with R4OS
0.87.13. At a user-requested desktop run, a fixed read-only STATUS query discovers
this guest capability. There is no image/revision allowlist or automatic image
change. A new deployment supplies the updated private process controller; old
helper packages remain readable and must be deployed again for desktop runs.

The host sends exactly one `DESKRUN /JSON /WAIT:10000 /WAITFRAME` launch for the
verified absolute Exchange Build `APP.R4X`. `/JSON` is first, including for syntax
errors. Short `before_submit` diagnostics are distinct from full request
receipts. The opaque original request, raw bounded SSH output, native phases,
error/errorlevel and process/window/content identity are durable. The native
u64 `process_generation` and `content` are decoded without precision loss and
exported as decimal strings, never JavaScript numbers. Phase snapshots are not
assumed to contain every transition.

Timeout does not terminate or negate a start. After timeout or ambiguous SSH,
only `/STATUS:<original-request>` is used, bounded by the original run deadline
and up to 45 seconds of receipt reconciliation. Neither `terminal:true`, status
code 0 in accepted/starting, nor error 13/14 proves application completion or a
failed launch. Late content after a timeout can confirm readiness. Missing
request identity yields **Launch outcome unknown**, with VM quarantine and no
replay. Status query errors never become pre-submission launch rejections.

Desktop retains process/reap ownership and performs native window association
and initial client resize. Studio's independent watchdog borrows only the exact
receipt process generation for output/completion/stop and runtime limits. Its
window observations also bind the original WINSVC broker generation. No app
source changes, SDK changes, assigned window IDs, synthetic resize or GUI wrapper
are used. DESKRUN status is not ongoing process monitoring. Before process
adoption, an unknown start cannot be cleaned up by the watchdog; its quarantine
requires explicit reconciliation and confirmed guest end. Existing VM images,
project pins, original tool declarations and frozen permissions remain intact.

The pending agent call returns when native content plus a current visible
process/window are confirmed. Unconfirmed content returns a separate readiness
result while the original bounded execution remains supervised. Captures require
that content receipt and check the process/window/revision around one QMP PNG
capture. They retain the request and u64 content receipt alongside the image.
This is a VM screen image with software Desktop-content evidence, not a physical
scanout assertion; visual criteria still require actual image assessment.
Desktop-consumed exit evidence remains unknown rather than becoming exit code 0.

The complete DESKRUN argument tail (options, quoted package path and app
arguments) is limited to 127 UTF-8 bytes. Studio rejects overflow and shell
control characters before launch. DESKRUN has no CWD argument; desktop apps use
the native Desktop directory and must resolve assets/output against their
module directory or explicit paths. Registered output collection always targets
the deployment directory; terminal/service CWD behavior is unchanged.

Primary sources: [DESKRUN](https://github.com/R4OSDev/r4os-app-desktoprun/tree/8ebe85aa7fb2032b12301cc6530fd2d79e185b83),
[Desktop consumer](https://github.com/R4OSDev/r4os-app-desktop/blob/7ba6305d4af4539677e95f8c99a5b14ac2400a02/src/rust/runtime/desktop_launch.rs),
[WINSVC wire contract](https://github.com/R4OSDev/r4os-service-windowservice/blob/0edb320c5b9dbc048b7470a9cfe4df0262476ddb/Contract/desktop_launch_v1.zig).
Validation: syntax, Zig AST checks, Studio build/TypeScript and lint passed.
A user-authorized smoke run on an isolated Full 0.87.14 VM built/deployed the
unmodified Zig SDK desktop starter and private helpers, confirmed native content
while the app remained running despite terminal:true, captured the correlated
1280 × 720 screen and confirmed generation-specific stop with quarantine release.
The image release manifest pins the exact DESKRUN/Desktop/WINSVC sources above.
Temporary project/VM data were removed afterward; the imported image is retained
without changing defaults. No automated test suites, agent inference, browser
functional tests or injected timeout/transport faults. Runtime receipts and
screenshot: Research/R4OS/Roadmap-Implementation/0.3.64/ in the workspace.


Version 0.3.63 zeigt den SSH-Ablauf in vorhandenen Session-Jobkarten mit Build-Zielpfad, Paket-/Startbereitschaft, Ausgaben und Belegen. Historische Daten bleiben unverändert lesbar. Die drei Desktop-Gastaufgaben in0.3.61 bleiben offen.

Version 0.3.62 wartet bei Deploy und Run intern im Agent-Harness auf Paketquittung, Terminalabschluss oder Servicebereitschaft. Bestehende Toolnamen, Argumente und eingefrorene Berechtigungen bleiben erhalten; kein Modell-Polling oder impliziter VM-Start.

Version 0.3.61 weist Desktopstart ausdrücklich mit native_desktop_launch_contract_missing zurück. Die drei Integrationsaufgaben bleiben offen, bis ein öffentlicher nativer Gastvertrag vorliegt; Deployment, Terminal und Service bleiben unabhängig nutzbar.

Version 0.3.60 startet bestätigte Exchange-Pakete mit eigener Prozessgeneration als Terminal oder Service. Normale Bootwechsel werden nach neuer SSH-Authentifizierung und vollständiger Paketprüfung gebunden; Desktop bleibt bis zum nativen Gastvertrag gesperrt.

Version 0.3.59 überträgt neue Pakete per create-only SFTP ausschließlich in den nachgewiesenen Exchange-Build-Ordner. Eigentumsbelege, vollständiges Rücklesen, begrenzte Inventur und Quotenprüfung erhalten alte oder teilweise übertragene Dateien.

Version 0.3.58 ergänzt den begrenzten Exchange-Build-Unterbaum mit rekursivem Offline-Import/-Export, atomarem journalgestütztem Baumwechsel und Browsernavigation. Laufende alte VM-Worker werden vor neuen verschachtelten Deployments gesperrt.

Version 0.3.57 führt die journalgestützte Exchange-Identität, read-only SFTP-Zielauflösung und getrennte Deployment-/Bereitschaftsverträge ein. Bestehende C:-Belege bleiben lesbar; Desktopstart benötigt weiterhin einen öffentlichen Gastvertrag.

Version 0.3.56 supplies the fixed R4OS SSH login automatically: user `r4os`,
password `rosebud`. VM Settings no longer accepts a guest username/password, and
new VMs need no Save access step. Existing explicit SSH disablement, Network
settings, VM identity and host-key verification remain in force. No tests or
VM/SSH/agent runs were performed; Python syntax, Studio build/TypeScript and lint
are checked.

## Automatic R4OS guest login (0.3.56)

All new SSH/SFTP and guest-control connections use the fixed R4OS default account.
Existing configurable login values are ignored, including values in legacy VM
access records. New VMs default to enabled development access without a saved
access record; an explicitly saved disabled setting remains disabled. Network
must still be enabled. Guest authentication failure reports a rejected default
login and never asks the user to enter another password.

VM Settings → Development access retains Enable SSH access, host-key inspection/
reset and Check access. Username/password inputs and API fields are removed.
Readiness from the previous configurable-login policy is invalidated, while the
VM-bound SSH host key and its image/system-generation binding are retained.
Metadata writes record credential policy `r4os-default-v1` and preserve schema-1
login fields with the fixed values for pinned workers and rollback releases.
Legacy records are not rewritten on reads; configurable values are ignored and
replaced on the next ordinary access-settings/readiness write. The password is
passed through the existing private temporary SSH askpass mechanism, not
returned by VM APIs or mounted into project/agent workspaces.

Existing session/tool profiles and component pins are unchanged. Development and
agent coordinators adopt the installed compatible release when idle; existing
workers keep their pinned release. No new host compatibility maintenance is
needed. This changes authentication only; deployment remains unchanged.

Version 0.3.55 enables Network by default for new VMs and adds Start project VM
in new agent sessions. The harness holds this single tool call until the fixed R4OS
default account authenticates over SSH and R4OS answers VER, then resumes the same
agent turn. Progress and the durable job remain visible while it waits. Existing
VM settings and session profiles are preserved. Deployment is unchanged.

## Agent VM startup and SSH readiness (0.3.55)

New VM forms and API creation default Network to enabled; an explicit false and
all existing VM configurations retain their value. The connection uses the
existing private SLIRP network and a temporary loopback SSH forward, with no
LAN/VPN guest listener.

New sessions use studio-tools-v3 and offer **Start project VM** under Session
settings → Tools → VM, enabled by default. The call selects only the project's
assigned VM. Studio supplies the R4OS default login automatically since 0.3.56;
Network and development access must be enabled. It starts a stopped VM
once, or observes the current boot of an already running VM. It does not compile,
upload files, build a guest helper, start an application or change VM settings.

The browser displays a durable vm_start job as the native tool stays pending.
The harness waits internally; the model needs no status-polling or sleep calls.
A fixed authenticated VER command must succeed with the current image, SSH host
key and observed boot generation before the tool returns success and Codex
continues the same turn. This confirms SSH readiness, not GUI/app readiness.
The VM lease wait is bounded at 90 seconds, readiness at 180 seconds and the VM
worker at 300 seconds. Invalid credentials, changed host keys/boots, stop and
timeouts return a clear failure. Stop cancels the owned wait/job and closes its
private connection; it leaves the VM running. Unconfirmed starts are never
repeated automatically, including after a coordinator or worker restart.

Existing sessions keep their native tool declarations and saved permissions.
**Create a new session for Start project VM**; v1/v2 conversations are not rewritten.
The readiness wait uses the start permission independently of Read development
job. VM/image/project/boot/lease/agent ownership checks remain enforced; credentials
and private transport paths are never exposed to the model or workspace.

This tool profile requires explicit additive host maintenance, not bootstrap
reinstallation. From the workspace root, as root:

```sh
python3 App/scripts/agent-sessions/install-vm-start-support.py
# Install Studio 0.3.55 through System → Updates → R4OS Studio.
python3 App/scripts/agent-sessions/install-vm-start-support.py --adopt
```

The first step updates only the known updater compatibility implementation and
keeps v1/v2 rollback releases valid. The second adopts the installed release only
with idle agent runs/worker units. Neither step restarts VMs, changes configuration
or rewrites session history. Custom updater code is preserved for review. Fresh
installations already include the new compatibility; existing coordinators still
need to adopt the installed release. Syntax, Studio build/TypeScript and lint are
checked for this release; no tests, VM starts, SSH probes, agent runs or project
build/deploy runs were performed.


Version 0.3.54 removes the Studio first-frame GUI workaround. New Zig/C desktop and subsystem projects keep the official SDK paint calls; Studio no longer generates or imports studio_gui.zig/studio_gui.h. The existing local Hello World source is restored to Window.beginPaint(), with the unchanged generated helper and its Studio-specific notice removed. Template identity advances to templates-v6; component pins and saved build history are retained. The replacement deployment/run approach is deferred. Python syntax, Studio build/TypeScript and lint checked; no tests or project/VM runs.

Version 0.3.53 completes the project editor with Quick Open (Ctrl/Cmd+P), literal saved-source search (Ctrl/Cmd+Shift+F), version-aware result navigation and documented limits. Search runs without a shell or index, skips generated/cache/Git directories, and reports incomplete or skipped results. All six editor subversions are implemented without tests or user-project feature runs.

## Project source editor (0.3.48–0.3.53)

Projects → project → Editor opens the Workspace file tree in navigation column
three and source tabs in the full main area. Folders load on expansion, with
100-entry pages. Click a file to edit it; tabs show relative paths and unsaved
changes. New file, New folder, Rename, Delete and Refresh are available in Files.
Deletion requires confirmation; folders must be empty, and creation/rename never
overwrites an existing target. Open destination drafts are preserved.

- Ctrl/Cmd+S saves the current file; closing a dirty tab offers Save/Discard/Cancel.
- Ctrl/Cmd+F opens in-file find/replace; standard undo/redo and indentation keys
  use each document's retained CodeMirror state.
- Ctrl/Cmd+P opens Quick Open by file name/path; Ctrl/Cmd+Shift+F searches saved
  Workspace text. Arrow keys select results; Enter opens the selected result.
- Files changed on disk keep the editor draft and offer Compare, explicit Reload
  and Save as. Save as creates a new file and keeps the original draft open.
- Navigation to Sessions, Settings, another project or System retains open files,
  undo and cursor/scroll state. Reload/closing the browser warns about drafts and
  uncertain operations. Unsaved drafts are held in memory, not crash-recovered.

The browser owns editor state and display; fixed unprivileged Python operations
under `scripts/projects/editor*.py` own file access. The Fastify module
`backend/src/modules/project-editor/` uses Projects browser sessions, allowed
Host/Origin and CSRF. Public contracts are in `shared/project-editor.d.ts`.
The API exposes tree/file reads, batched status, mutations, operation receipts
and bounded search under `/api/projects/<uuid>/editor`. It cannot select a host
root, shell command, SDK directory or VM. No LLM account/session or VM is needed.

Only `Data/Projects/<uuid>/Workspace/` is accessible. Every path is resolved with
no-follow directory descriptors; symlinks, hardlinks and special files cannot be
edited. A missing `module.R4MF` can be repaired without layout migration. The
512 KiB UTF-8 file limit, 20 open/loading documents across Studio and 10,000
entries per directory bound the initial scope. Binary/non-UTF-8/oversized files
show a status. UTF-8 BOM, LF/CRLF and absence of a final newline are retained;
mixed line endings are read-only. Root `Agents.md` uses the existing 32 KiB
validation and filename rules shared with Settings. Manifest/Cargo edits do not
change project component pins or bypass SDK validation.

Save binds both byte SHA-256 and file revision. Mutations take the exclusive
project lifetime lock and confirm idle runs/jobs and stopped historical workers.
Reads and local drafts remain available during runs; only saved files enter a
build's existing source snapshot. Save does not start build/deploy/run. File
staging and durable request journals live outside Workspace under the private
project `.studio/editor/` directory. Atomic publication uses fsync; create and
rename do not replace targets. Lost responses retain the same request in browser
session storage; Retry operation checks/reuses its receipt rather than issuing
a new mutation. Interrupted requests are never replayed automatically at startup.
Project deletion removes these private records with the UUID directory, warns
about drafts and waits for unresolved local editor operations.

Visible editor status runs as one batched request for open-file metadata every
five seconds and on focus/save, paused while the browser is hidden. There is no
recursive polling, filesystem watcher, shell search or index. Project search is
literal and limited to 2,000 files, 2,000 directories, 10,000 entries, 16 MiB read,
200 results and three seconds per request, with one browser search in flight per
project. It excludes `.git`, `.zig-cache`, `zig-out`, `zig-pkg`, `target`, `build`,
`.R4OSRust` and `node_modules`. Skipped entries and incomplete results are shown.
Result navigation rereads the current version and preserves dirty tabs; stale
line numbers are not applied to a changed file or draft. There is no project-wide
replace, recursive deletion, executable preview, LSP or compiler process.

CodeMirror is bundled locally and loaded on demand, without a React wrapper or
CDN. Exact MIT dependencies and resolved transitive packages are pinned in
`package.json`/`pnpm-lock.yaml`: state 6.7.6, view 6.43.15, commands 6.11.1,
language 6.13.1, search 6.7.2, lang-rust 6.0.2, lang-cpp 6.0.3, lang-json 6.0.2,
lang-markdown 6.5.2 and legacy-modes 6.5.5. Rust/C use official language modules;
Zig/.zon and R4MF use local token modes; JSON, Markdown and TOML are supported,
with plain UTF-8 text as fallback. Syntax highlighting is not type checking.

Validation for these six subversions: source review, Python syntax compilation,
Studio build/TypeScript and lint. No tests, sample projects, browser/agent/guest
runs or user-project build/deploy/file operations were performed. Each subversion
is separately published, tagged and installed through the regular updater.
Workspace documentation: `Docs/Project-Editor.md`; release evidence:
`Research/R4OS/Roadmap-Implementation/0.3.48/` through `0.3.53/`.

Version 0.3.52 adds batched visible-editor file status, focus refresh and explicit conflict comparison, reload and Save as. Dirty drafts survive section/project changes and active agent jobs; lost mutation responses retain the original request. Project deletion warns about editor drafts and waits for unresolved operations.

Version 0.3.51 integrates the Workspace file tree, source tabs and explicit save into Projects → Editor. New file/folder, rename and confirmed deletion use version-bound receipts and the existing project lifetime locks. Drafts survive navigation within Studio; file operations remain independent of agent tools and VM access.

Version 0.3.50 adds the locally bundled CodeMirror 6 source editor core with independent document state, undo history, cursor/scroll preservation, keyboard save and file search. Rust/C use official language modules; Zig/.zon and R4MF have local syntax modes, with JSON/Markdown/TOML support. Language assets load on demand, without CDN or language-server processes.

Version 0.3.49 adds explicit Workspace save/create/folder/rename/delete operations. Project lifetime and worker admission protect writes; byte/entry identities, private same-filesystem staging, non-overwriting rename and durable receipts preserve newer files across retries. Agents.md keeps its existing instruction rules and project pins remain unchanged.

Version 0.3.48 adds the protected project editor read API with paginated Workspace directories, stable bounded UTF-8 reads and byte identities. The editor can read a Workspace whose manifest needs repair, without creating sessions or development jobs. Links, hardlinks, unsupported formats and oversized files remain unavailable for editing.

Version 0.3.47 Project Settings → General now includes Clear build cache. The fixed project operation waits for idle agents, jobs and workers, owns the project lifetime lock, and removes only the detached private compiler cache. Persistent request receipts protect retries and newly rebuilt caches; source files, pins, sessions, artifacts, VMs and shared packages stay in place. Unsaved settings remain unchanged.

Version 0.3.46 Components now has one SDK view with its matching Contract and Libraries, installation states and shared download/default actions. Previously selected Contract/Libraries views lead to SDK. Interrupted browser requests retain their operation identity for explicit retry, including after a page reload; existing project pins remain unchanged.

Version 0.3.45 SDK download and default selection now use one durable component-service job for SDK, its exact Contract and Libraries. Existing packages are checked and reused without changing their archive identities; default activation commits the complete set atomically. Request receipts, manifest/profile binding and service capability checks protect retries and mixed releases. Existing project pins remain unchanged.

Version 0.3.44 SDK version checks now resolve the published SDK-Release.json into an exact SDK, Contract and Libraries set. The bounded metadata cache retains archive origins and checksums separately from existing installations; status polling stays local and existing defaults and project pins remain unchanged.

Version 0.3.43 adds Reset virtual machine and Reset Exchange Partition beside Delete in VM settings. Confirmed stopped-only resets atomically replace the system overlay on the bound image or the entire Exchange image/share/sync state, preserving the other storage and VM identity/settings/login. Durable request receipts prevent repeated resets. Cross-process maintenance reservations block new VM jobs; active jobs/exports prevent reset. System generations invalidate old host-key/readiness trust even for the same image; credentials remain bound to the VM. Syntax/build/TypeScript/lint checked; no tests and no VMs reset or started.

Version 0.3.42 adds Projects → Settings → Agents.md with a plain text editor, Save changes and Cancel. Hash conflicts retain the draft, reload/discard is explicit, navigation/reload protects unsaved edits and saving is disabled while project runs/jobs are busy. Missing files show the title/description draft and are created on Save. The current frozen file supplements the global prompt from the next accepted run. Syntax/build/TypeScript/lint checked; no tests, browser, agent or guest runs.

Version 0.3.41 freezes Workspace/Agents.md text and SHA-256 at run admission alongside the global system prompt. Start/resume applies both explicitly, with global instructions taking precedence and new versions replacing earlier Studio instructions. Native file discovery stays disabled. Existing admitted runs retain their old snapshot; new web requests require coordinator support and cannot silently fall back. Thread/history and project pins are preserved. Syntax/build/TypeScript/lint checked; no tests or native runs.

Version 0.3.40 creates Workspace/Agents.md with Titel and Beschreibung during durable project publication. A fixed protected API reads/saves the 32 KiB UTF-8 file with hash conflicts and exclusive project maintenance locks. Existing files and pins remain unchanged; reading a missing file returns a draft. Reserved v4 creation requests retain their original file map. Syntax/build/TypeScript/lint checked; no tests or project/agent/guest runs.

Version 0.3.39 combines execution target binding and its VM observation. All
deployment files are downloaded through one authenticated SFTP batch, then each
size and SHA-256 is checked before launch. Host keys, project/VM/image/boot/lease
bindings, quarantine, stop checks and the single acknowledged start remain required.

Screenshot readiness and capture share one private VM request. The bridge checks
the VM service and QMP running status; lease checks still bracket capture. Validated
PNG bytes are durably published and forwarded directly to the native agent reply,
without rereading the file or issuing another evidence request. The coordinator
reauthorizes the agent before returning the image; native model/tool permissions
are still checked. Tool receipts and UI events retain only image references.
Later evidence retrieval and resumed replies open the stored file once, check its
type, size and SHA-256 against exactly those bytes, and return the same buffer.
Existing operations remain available to old workers. New workers use the legacy
path only after an explicit unsupported-operation response, never after timeouts
or lost receipts. No SDK changes, host maintenance or data migration.
Build/TypeScript, Python syntax and lint checked; no tests, browser, project,
agent or guest runs at the user's request. No new timing measurements.
Workspace details: Docs/Run-Capture-Optimization.md.

Version 0.3.38 reduces repeated build/deploy validation and retains private
compiler caches across jobs. Session ownership uses database metadata; artifact
bytes and provenance remain fully checked at admission and in the worker.
Cached helper cleanup can reuse its just-verified receipt. Catalog discovery and
the semantic/contract plans retain manifest checks without a separate validate
process. Source capture hashes while copying; the build worker independently
checks the captured bytes before compiling.

Each deployment file is uploaded and completely read back in one authenticated
SFTP batch. Local/remote hashes, size limits, create-only publication, host keys,
VM/boot/lease bindings and uncertain-effect handling remain required.
Zig local/global and SDK Rust target caches live under
`Development/Cache/<identity>/`, scoped to the project, exact component pins,
language/role and build/cache implementation. An exclusive host lock covers each
use. Only compiler cache directories enter the sandbox; sources, output, HOME,
Cargo configuration and trusted SDK tools remain fresh per job. Changed bindings
use another cache; successful scratch cleanup retains caches and project deletion
removes them with the project. No cached success replaces a fresh SDK build,
container inspection or artifact receipt. No SDK or host protocol migration.
Build/TypeScript, Python syntax and lint checked; no tests or project/guest/agent
runs at the user's request. Workspace details: Docs/Build-Deploy-Optimization.md.

Version 0.3.37 avoids repeated full component checks when creating a project.
The options dialog reads installation metadata and the checksum-checked published
SDK capability catalog without running compilers or scanning the Rust installation.
Older Zig metadata without a binary checksum still needs one compiler-file hash.
Submitting verifies the required components once and reuses that context through
publication. Zig/C skip the Rust toolchain; Rust verifies its installation once,
including PowerShell, and reuses those file hashes for its pins. Interrupted
creation revalidates the saved pins when resumed. SDK checks and durable file
publication remain required. No persistent verification cache or data migration.
Build/TypeScript, Python syntax and lint were checked; no tests or project/agent/VM
runs were performed at the user's request. Workspace details: Docs/Project-Creation.md.

Version 0.3.36 makes the session fill its content area without outer margins,
border or rounded corners at every breakpoint. Narrow layouts can grow beyond
their preferred session height to fill the available space. Internal message
and composer spacing stays readable. Build/TypeScript and lint passed; no tests
were run, as requested.

Version 0.3.35 removes the project heading above an open session and the model
subtitle below its title. The session title is now the main heading, leaving
more vertical space for the conversation. Model selection stays in the composer.
Build/TypeScript and lint passed; no tests were run, as requested.

Version 0.3.34 places Account, Model, Reasoning and Fast Mode dropdowns below the
message field, aligned left beside the send controls. Choices save immediately
with the session revision and apply to the next run. Selection is locked during
runs, uncertain send retries and saves. Model/account changes retain compatible
reasoning and Fast Mode choices; unsupported choices use the selected model's
defaults. Session settings now contain the name and tool permissions.

Fast Mode defaults to Off for existing and new sessions. Availability comes from
the connected account's model catalog. Each run freezes the choice; Codex's native
Fast Mode feature and `serviceTier` are set explicitly for start, resume and turn
(`priority` for On, `default` for Off). Switching Off clears a tier remembered by
the native thread. Existing thread history, tool profiles and provider credential
storage are preserved. The additive JSON setting needs no database migration or
host maintenance. Build/TypeScript, Python syntax and lint passed; no automated,
browser or native agent tests were run, as requested.

Version 0.3.33 groups consecutive tool and terminal calls from the same run into
expandable blocks between messages. Compact blocks show three single-line tool
summaries and scroll to additional calls. Each call opens independently; opening
a call also expands its block. Collapsing the block closes its tool details again.
Arguments, outputs, screenshots and development job cards remain available inside
their calls. New calls follow the scroll position while the user stays at the end.
This is a browser presentation change for both saved history and live events.
Build/TypeScript and lint passed; no tests were run, as requested.

Historical behavior in 0.3.32 (removed in 0.3.54): Studio adapted newly generated Zig/C desktop and subsystem starters in
the project workspace. A small Studio helper opens the first paint with a
480 × 240 canvas when Desktop has not published a positive client size yet.
Once available, the actual client size is used unchanged, including smaller
windows. Frame failures still propagate through the SDK's normal paint lifecycle.
Rust's separate drawing facade is unchanged.

Installed SDK/Contract files, manifests and component pins are unchanged. There
is no launch delay or change to the guest starter. Existing project sources are
not automatically migrated; the reported Hello World project was explicitly
adapted. Compiler-backed startup/resize/error regression checks, real C-header
compilation, application build and lint passed. The user will perform the VM and
screenshot test; this release does not claim a newly verified guest run.

Version 0.3.31 binds development credentials to the VM UUID. Existing saved
logins work after an image change without re-entry or another Save access.
The replacement image must accept that login. Studio reports authentication
failures without discarding the stored credentials.

Image identity now scopes SSH host-key trust and readiness only. A replacement
image is authenticated with the VM login and its host key is learned again;
unexpected key changes within the same image still fail verification. Existing
per-VM records remain compatible; no setup, migration or host maintenance is
required. Project/image/boot leases and job bindings remain enforced.

Version 0.3.30 corrects the Codex sandbox context sent to new and resumed
sessions. Studio exposes a writable project through its dynamic tools; Codex
now receives `workspace-write` instead of the contradictory `read-only` policy.
Resume explicitly replaces the saved policy, preserving the thread and context.
Native tools remain disabled, the inference process keeps an empty virtual cwd,
and Studio still enforces every frozen tool permission and filesystem boundary.
SDK, Contract and compiler roots remain read-only. No host maintenance is needed.

Version 0.3.29 removes VM-image, release/kernel and project-component approval
lists from development access, job admission, deployment and execution workers.
The runner uses one image-independent SSH/SFTP and process adapter. Authenticated
`VER` responses supply guest release/kernel information without version matching.
New images and project SDK revisions need no Studio qualification entry.

Project pins still identify build inputs; VM revision/image/boot bindings, explicit
Development access, host keys, leases, full transfer readback and owned process
handles remain enforced. The guest helper keeps its own reproducible build pins
in `shared/r4os/development-runner.json`; these are not compared with application
pins. The runner implements Terminal, Desktop and Service execution. Other roles
still need their corresponding loader or test host. Runtime failures remain
visible rather than being inferred from a release approval list. Existing
deployment labels do not invalidate an otherwise unchanged target on update.

Version 0.3.28 removes Studio's SDK/Contract/compiler revision approval list.
New projects use the selected components and their published SDK metadata;
SDK/Contract source hashes, compiler requirements and existing project pins
remain binding. There is no new language minimum-version policy.

The adapter resolves `SDK-Release.json` for the selected SDK, checks its exact
SDK/Contract identities, and verifies the exported host toolset and capability
catalog. The first preparation downloads these small official SDK assets into
`Projects/.studio/tools/<component-fingerprint>/`; subsequent project creation,
builds and isolated agent tools reuse the checked cache. Shared SDK/Contract
folders remain read-only. Accepted projects also pin the release, tools profile,
archive and capability hashes. Compatible new revisions need no Studio entry.

Zig, C and Rust use the SDK's common project creator and canonical template file
maps. SDK 0.64.90 exposes all seven Studio module types for all three languages.
Studio preserves entered subsystem identity/formats when expanding SDK examples.
The verified private PowerShell runner is reused; SDK-pinned compiler versions
still come from SDK tooling metadata. Rust toolchain update profiles are derived
from the selected SDK release, with no fixed SDK revision selection. A compatible
installed compiler can serve a newer SDK without changing the user's defaults.

Build and agent namespaces expose the selected SDK tools and verified compiler
layout. Rust build receipts support the current SDK receipt schema 2. VM
admission no longer compares application SDK pins against a Studio revision list;
artifact/input identity checks and the image/role-specific runner adapters remain.
Existing guest helpers retain their own Studio infrastructure dependencies.
Project pins, global standards, existing sessions and running VMs are not migrated.

Validated with the actual selected SDK 0.64.90 / Contract 0.64.44: all 21
language/module combinations created and SDK-validated, isolated Zig/C/Rust
terminal builds passed, browser creation including a Rust subsystem through
320 px. 32 backend, six project, 27 agent, 34 development and seven component
tests, build/TypeScript and lint passed. Future synthetic SDK/compiler identities
are accepted while mismatched dependencies, hashes and changed pins are rejected.

Version 0.3.27 adds **Projects → Settings → General → Delete project**.
A separate dialog names the selected project and asks for confirmation. Deletion
removes its UUID directory, workspace, sessions/native history, build artifacts,
and attributed worker/runtime records. The assigned VM and files already deployed
to it are kept, as are other projects, shared components and global settings.

The DELETE API requires the Projects browser session, CSRF, allowed host/origin,
`{ revision, confirm: true }` and the current project revision. Active runs/jobs,
held workspace reservations and unconfirmed guest effects block deletion. A shared
project lifetime lock prevents new sessions/jobs racing with deletion; a still
running older coordinator must adopt this release before deletion is admitted.
Projects without host support can be deleted if no agent/development history needs
reconciliation. No model turn, build, guest connection or VM action is started.

A durable catalog journal records confirmed intent before removing any data.
Interrupted deletions remain visible as **Deleting…**, open General with **Retry
deletion**, and resume on startup. Completed deletion removes project metadata and
creation responses, retaining only opaque original request ID/hash fingerprints
to prevent a delayed create retry from restoring a deleted project. This is not
an archive. Shared SDK caches/releases are not garbage-collected. Browser drafts
for this project's known sessions are cleared from the current tab on success.
The catalog remains schema 1 with additive tables; no privileged host maintenance
is required. Older releases preserve but cannot finish pending deletion journals.

Validated: 32 backend tests, three focused deletion tests, 27 unprivileged agent
tests and 34 development tests, build/TypeScript and lint. Browser confirmation,
Cancel/Escape, active/stale guards, interrupted-deletion retry, draft cleanup and
layouts down to 320 px passed. SDK creation integration uses an isolated copy of
the qualified 0.64.66 profile; user-selected component defaults are preserved.

Version 0.3.26 adds **System → Settings → System Prompt**. One shared prompt
applies to every project and both new and existing sessions. Save changes stores
it globally; Reset to default immediately restores the shipped R4OS development
prompt. Cancel discards editor changes. Updates apply from the next accepted run;
already accepted/running runs retain their captured instructions.

The default lives in `shared/system-prompt.json`; the private override and its
revision live in `Data/Projects/.studio/Settings.sqlite`, outside every workspace
and tool mount. No SDK, project sources, pins or provider credentials are changed.
The settings API uses its own browser session, CSRF token, host/origin checks,
UTF-8 limit of 32 KiB and optimistic revision checks. Identical retries return the
stored result. Conflicting edits retain the draft and require an explicit reload.
Invalid or corrupt storage is preserved and reported, never reset implicitly.

Each durable run config captures prompt text, revision and SHA-256. Workers pass
that capture as native `baseInstructions` on `thread/start` and `thread/resume`;
the user message stays separate. Native thread IDs, history and v1/v2 tool
declarations are preserved. This field was qualified with the pinned Codex
0.163.0 binary: separate processes used prompt A, prompt B and the restored
default in the same thread while retaining its context. `developerInstructions`
alone accepted a resume override but retained the earlier behavior in that live
probe, so Studio does not use it for this feature. Versioned source:
[thread parameters](https://github.com/openai/codex/blob/129b8ec7ee6f4511557a4856279f529025c25af4/codex-rs/app-server-protocol/src/protocol/v2/thread.rs).

No host maintenance is needed. Data/worker protocols remain 1 with an additive
run-config field and a separate settings store schema 1. A new worker admitted
by an older coordinator captures a missing prompt once before inference. Older
workers keep their original release; rolling back to a release without this
feature preserves the settings store but does not apply the global prompt.

Version 0.3.25 completes the qualified agent → build → deploy → run → inspect
workflow with conservative recovery, VM job serialization and release continuity.
Reconcile receipts checks the original immutable worker binding and committed
artifact/readback/guest-close evidence. It never recompiles, transfers or launches
an application. Missing or damaged receipts remain preserved as unknown. A known
VM stop can confirm process end while the application result stays inconclusive.
Startup only adopts live workers and matching local committed receipts; it starts
no model turn, VM, build or guest test.

Jobs sharing a VM wait for its reservation, bounded to 180 seconds, and recheck
scope before the first guest action. Independent VMs can run in parallel. Lost
input/start replies are not replayed. Unknown effects close further agent tool
admission; generation-owned guest cleanup remains independently bounded. A lost
boot observer cannot certify continuity: redeploy or reconcile explicitly.

QEMU forwarding removal recognizes its exact success/missing-rule responses.
Under the VM reservation, stale owned rules and their temporary authentication
files are retired; live/foreign reservations stay intact. Primary interface:
https://github.com/qemu/qemu/blob/v10.0.0/net/slirp.c . No guest service is exposed
outside loopback. VM input still targets the owned SDK process/window only.

Successful, hash-verified builds retire their private Work scratch. Captured
Inputs, Artifacts, Evidence, publication/close receipts, failed/unknown scratch,
components and original releases remain available until explicit maintenance.
Input/package/output/image budgets continue to apply; there is no automatic
project/session deletion or component/release garbage collection.

Explicit host maintenance before installing this release:
`python3 scripts/project-development/install.py`,
`python3 scripts/agent-sessions/install.py`, and
`python3 scripts/project-development/install-update-compatibility.py` as root.
These preserve the existing bootstrap/configuration and active workers/VMs.
Agent/development runtime directories survive full coordinator stop/start. The
last script only upgrades a recognized host updater while idle; downloaded
updates never run a privileged installer. Host/worker/data contracts remain 1,
with explicit v1/v2 agent-profile support; old v1-only releases remain read/rollback
targets and cannot silently replace a v2 conversation. Running workers retain
their original release, inputs, pins and guest helper across a web update.

## Agent development tools and settings (0.3.24)

Version 0.3.24 connects the development pipeline to seven qualified agent tools:
`studio.build_project`, `studio.deploy_project`, `studio.run_project`,
`studio.read_development_job`, `studio.stop_development_job`, `studio.capture_vm`
and `studio.send_vm_input`. Each new session uses `studio-tools-v2` with sixteen
independent permissions, initially on. Original `studio-tools-v1` conversations
retain their nine declarations and exact native thread; additional tools there
require a new session. Settings never silently replace or migrate a thread.

The private broker rechecks the active worker PID/birth, run/settings snapshot,
profile, project pins, individual permission and session ownership. Artifacts and
deployments cannot be borrowed from another session. Queued input rechecks the
caller immediately before the guest effect. Terminal namespaces remain isolated
from VM sockets, broker sockets and credentials. A completed agent turn leaves
an admitted bounded execution running; User Stop closes admission and stops its
owned development jobs even with the agent stop-tool permission disabled.

Run calls may override arguments, time limit and explicit criteria for that job
without rewriting saved project settings. Native image responses are generated
only for models whose catalog declares image input. Studio history stores opaque
hash-bound attachment references; the RPC image is transient. An agent visual
assessment records its model/run identity and an image captured in that same run.
Job assertions, visual assessments and lifecycle outcomes remain separate.

Projects → Settings → Run & Test provides the pinned target, arguments, time limit,
exit/output/file/service/visual criteria and explicit Save/Cancel with revisions
and dirty-navigation protection. Session settings groups rights into Files,
Terminal, Build and VM, with capability reasons independent of switches. Tool
cards show live durable jobs, paged diagnostics, trusted PNG attachments and an
independent Stop job action. Reopening/reconnecting reads state and starts no job.

## VM observation and explicit checks (0.3.23)

Version 0.3.23 adds image-backed observation, owned console/GUI input and explicit
Run & Test assertions to the durable build/deploy/execution pipeline. Settings
freeze arguments, the deployment working directory, a 1–300 second limit, optional
exit/output/file/service-response criteria and a visual criterion. No criteria
means `not-run`; missing evidence means `inconclusive`, never an invented pass.
Automatic assertions and attributed user/agent image assessments remain distinct.

Only registered uppercase 8.3 output files in the owned deployment are collected
(up to eight, 64 KiB each), with content hashes and source receipts. Service checks
invoke the SDK's bounded operation 1 and compare its actual response; endpoint
availability alone is an observation. Console output remains combined, bounded,
paged and explicitly incomplete when the guest loses bytes. Crash/exit/timeout
and cleanup evidence remain associated with their exact process generation.

Job capture reuses QMP PNG through the private VM broker, bounded to 384 KiB and
1280×1024. Each immutable receipt records time, VM boot, process and GUI revision.
Protected evidence endpoints provide bytes and 32-item history pages; each job
retains at most 128 attachments. No credentials or base64 enter browser logs.
Native Codex 0.163.0 image responses use `inputImage.imageUrl`, qualified against
an actual image-capable model. Seven agent calls and their UI follow in 0.3.24.

GUI input targets the owned exact-generation process through public R4DESK logical
events, with a currently focused visible window and a matching image no older than
30 seconds. Supported keys are Enter, Tab, Escape and Space; clicks use bounded
client coordinates and paired down/up events. Pending button release is retried
only for that generation. This is not global physical-key or clipboard emulation.
Console text uses typed native events (64 Unicode characters per request), consumed
through the SDK console-event reader with an explicit R4DESK import. Applications must declare that input dependency in their manifest; accepting an
event does not prove that application code consumed it. Manual
controller admission respects the active VM lease. Duplicate action IDs return
the original receipt; lost input replies are never automatically replayed.

An independent guest watchdog survives SSH loss. Library, driver, protocol and
subsystem execution remain unavailable without qualified test hosts. Desktop can
consume a GUI completion before Studio: process closure is confirmed separately
and the exit code then stays unknown. An intentional invalid-opcode fixture in
Full 0.86.42 halted the whole guest; Studio preserved `unknown`, its screenshot and
the VM quarantine, without replay. Guest crash isolation is an external R4OS
limitation. See guest/development-helper/README.md.

## Verified project deployment (0.3.21)

Projects expose scoped deployment admission and receipts under
`/api/projects/:id/development/deployments`. Input is an owned completed artifact,
request UUID and project/settings revisions. The server resolves the assigned VM,
checks exact component/image identities and requires configured development access.
It may start that assigned VM; Network, image and other VM settings are preserved.
Active VM jobs block project reassignment. Repeated requests keep their original job.

A separate immutable-release VM worker retains a cross-process VM reservation and
checks the current assignment/boot before guest effects. It builds the small
versioned Studio helper using the pinned official SDK in a credential-free build
namespace, then authenticates the guest and verifies its active release/kernel.
The compiler cannot access VM sockets, disks or credentials. The VM worker has
only the additional private development-runtime access required by SSH.

Guest packages use owned short project/deployment directories and full UUID
ownership receipts. SFTP creates new files only; complete byte readback verifies
the app module, helper and package descriptor. Existing/foreign directories and
files are preserved. Success requires a matching helper handshake and a durable
deployment receipt containing source, manifest, package, pins, target and hashes.
A deployment starts no project application. Lost transfer receipts remain unknown
and are not replayed; Stop preserves partial guest files for inspection.

The helper reports available process/file/service interfaces; console input and
owned project execution follow in 0.3.22. SDK support and guest role qualification
remain distinct. New agent calls and their controls follow in 0.3.24.

Explicit host maintenance via scripts/project-development/install.py installs the
narrow VM-job service and preserves the shared runtime directory on coordinator
restart. Existing bootstrap, VM processes and independently pinned workers remain
unchanged. Private deployment state adds a compatible table to schema 1; older
build workers ignore it.

## Private VM development access (0.3.20)

VM Settings includes Development access and Check access. Since 0.3.56 Studio
automatically supplies the fixed R4OS login, r4os / rosebud. Only VM access settings,
host-key trust and readiness receipts persist in private Studio storage outside
the workspace, together with fixed schema-1 login fields for older workers.
Responses return the username, policy and public fingerprint only.
Network must be enabled (new VMs default to enabled since 0.3.55). Readiness requires authenticated VER,
the exact release and active kernel, a pinned host key and the current observed
VM boot. QEMU running alone is not readiness. The SSH/SFTP client hashes are part
of the qualified execution profile; completed connections are not multiplexed.

VM operations share cross-process flock reservations. Manual VM changes, reset,
stop, exchange writes, deletion and console admission respect a development
reservation; distinct VMs remain independent. The private VM bridge reuses the
existing manager and RAM admission, checks VM/image/project revisions and a held
private reservation token, and exposes fixed operations only. Neither it nor
credentials/QMP/VNC sockets are mounted into agent/compiler namespaces.

A separate private development-qmp.sock observes resets without occupying the
original management monitor. New VM starts create both sockets. Existing running
VM workers are preserved and need an ordinary stop/start before development access
can use this observer. A changed/lost boot invalidates previous readiness and
targets. Guest SSH forwarding binds an ephemeral loopback port only and is removed
after the access operation; uncertain forwarding intents remain recorded privately
for explicit recovery. No guest services are exposed to the LAN or VPN.

Run the updated scripts/project-development/install.py as explicit host maintenance.
For an existing 0.3.19 host, restart only the idle development coordinator after
installation so its systemd namespace gains read access to fixed VM metadata and
the private monitor. Build workers retain inaccessible VM/provider mounts. The
installer preserves existing bootstrap, workers and VMs. Actual guest deployment,
owned execution and agent tools follow in the remaining roadmap releases.

## Durable project builds (0.3.19)

Projects expose scoped development options, settings, build admission, job output,
Stop and artifact metadata under `/api/projects/:id/development/`. Browser session,
CSRF, Host and Origin checks apply. Build requests bind project/settings revisions
and an idempotency key; retries do not create another build.

The separate unprivileged development coordinator starts one immutable-release
worker per job. Explicit host maintenance is `python3 scripts/project-development/install.py`
as root; this adds only fixed services and narrow unit permissions and preserves
the existing bootstrap. Running workers survive a Studio update. Recovery records
uncertain jobs without replaying them. Limits allow two host jobs and one per project.

`Development/Development.sqlite`, immutable `Inputs/`, `Artifacts/` and bounded
`Evidence/` are outside the agent workspace. Capture includes uncommitted sources,
checks for concurrent edits and rejects links/special files and input paths over
240 UTF-8 bytes. Generated caches and
old outputs are excluded. The worker uses pinned SDK validation and build paths in
a Bubblewrap namespace with no network, provider state or VM sockets and read-only
components. The canonical Zig/C SDK wrapper prevents project build scripts from
selecting different components; Rust uses the official locked/offline build driver
with explicit roots and all SDK technical checks intact.

Only a fresh module passing the official SDK container inspector is published
atomically with source/manifest/component hashes. Failed builds retain diagnostics
and expose no successful artifact. VM deployment/execution, browser controls and
the seven new agent tools follow in the remaining roadmap releases. An internal
agent snapshot channel already preserves its existing workspace lease, serializes
with file/terminal admission and rejects capture while a terminal is live; the
public build endpoint never accepts an agent owner override.

## Development qualification and contracts (0.3.18)

Studio now records exact execution qualification profiles separately from SDK
build capabilities. The pinned SDK 0.64.66/Zig 0.16.0 profiles were exercised in
private Full 0.84.47 and 0.86.42 VMs: Zig, C and Rust console modules, SFTP
create-only publication and complete byte readback, actual exit status, owned
generation-bound process handles, stale-generation rejection, completed output,
graceful close, timeout and owned kill/reap. Existing VM bindings and all defaults
were preserved. Full 0.86.42 was downloaded through the normal Updates UI.

The checked-in `guest/development-probe/` imports R4SYS and R4DESK; isolated child
console creation is a R4DESK API. Its output is collected explicitly so child
output cannot mix with guest control replies. The qualified SSH service closes
its connection after a completed session channel, so the adapter does not assume
OpenSSH multiplex reuse. Exact image/component hashes, not version labels, select
the profiles in `shared/r4os/development-profiles.json`.

`shared/project-development.d.ts`, `shared/development-host.json` and
`guest/PROTOCOL.md` define the Studio job/evidence/target contracts and limits.
Jobs, deployments, guest processes and check verdicts are distinct identities and
states; native u64 process generations remain decimal strings. Unknown roles,
images or changed pins fail closed. GUI/service and other role adapters remain
unqualified here. These foundations do not yet expose general Build/Deploy/Run
endpoints or new agent tools; implementation continues in the following releases.
Source, qualification and retained evidence are documented in the workspace's
Docs/Project-Build-Run.md and Research/R4OS/Agent-VM-Development/.

## Projects, sessions and agent runs (0.3.17)

Projects store their immutable UUID and SDK/Contract/compiler pins in
`Data/Projects/Projects.sqlite`. Sources, manifests and build outputs live in
`<project-uuid>/Workspace/`; session metadata/events/receipts in
`<project-uuid>/Sessions/Sessions.sqlite` and native Codex history in
`Sessions/<session-uuid>/Codex/`. Opening or creating a session starts no inference.

Projects → Sessions lists New Session and saved sessions. The main pane provides
chat/history, live file/terminal results, Send/Stop and Session settings. Nine
independent tool switches default on. Each explicit run maps to one native Codex
turn, with durable request identity and a frozen settings/pin snapshot. One run
uses a project's shared workspace at a time; at most two runs execute per host.
Editor and general build/deploy endpoints remain planned.

The unchanged official Codex 0.163.0 binary is bound to SHA-256
`399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`.
A qualified model catalog and feature profile disable native I/O tools and
instruction/extension discovery. Only registered Studio dynamic tools perform
project I/O, in a separate bounded Bubblewrap namespace. The credential-bearing
Codex process sees an empty virtual cwd; project commands see the selected
workspace and read-only pinned components, without credentials or session data.
Native history/compaction remain owned by Codex. Studio neither copies tokens nor
reconstructs context from the visible chat. Provider auth/refresh locks use the
one original physical Codex-managed provider store.

Linux/systemd, rootless Bubblewrap and the existing unprivileged Studio user are
required. Explicit host maintenance (never run automatically from a download):

```sh
sudo python3 /opt/r4os-studio/current/scripts/agent-sessions/install.py
# When upgrading the pre-agent updater to the declared agent protocol 1:
sudo python3 /path/to/reviewed/App/scripts/agent-sessions/install-update-compatibility.py
```

The installer preserves existing bootstrap/configuration and running workers/VMs.
A fixed Unix-socket coordinator starts separate bounded run units. Worker and
ExecStopPost stay bound to their original immutable release. A compatible newer
coordinator is adopted at idle; older coordinators need one explicit service
restart after their current runs finish. Neither browser close nor web update
stops a run. Host boot reconciles state without launching new inference. Queued
or incomplete outcomes become unknown/interrupted; tools with unconfirmed receipts
are never automatically repeated. Actual effects and native history remain intact.
Send an explicit follow-up after inspecting an uncertain result.

`shared/update-host.json` declares host/data/VM-worker protocol 1 plus agent
host/worker/data protocol 1. The targeted compatibility maintenance retains old
releases as rollback targets and rejects unknown/newer contracts. It adds no root
execution path for downloaded service scripts. New agent workers follow the
current compatible release; existing sessions retain their qualified engine pins.

File writes require current hashes; individual writes are atomic. Multi-file
patches use the official parser and may leave reported partial changes. An enabled
terminal can perform file operations independently of the file-tool switches.
Commands have no network, bounded output/time, four simultaneous process handles,
a 256 MiB file limit and a run cgroup limited to 2 GiB/256 tasks/200% CPU. Stop is
available independently of the agent termination permission. This provides host
app development, not a guest/deploy runner in that original increment. Global
system prompt management is available from 0.3.26; Skills/AGENTS.md management,
plugins, hooks, memory and subagents remain outside its scope.

Legacy projects are never moved automatically. As the data owner run
`python3 scripts/projects/migrate-workspaces.py <uuid>`; `--rollback` restores an
unchanged migrated tree. The migration preserves identities, pins and individual
edits, journals interrupted moves and refuses ambiguous layouts. Roll sources
back explicitly before using a pre-Workspace build helper.

Session/run endpoints reuse Projects browser sessions, CSRF and Host/Origin
checks. SSE replays durable sequence IDs after reconnect; uncertain submissions
retain the original request UUID in browser session storage. Assistant messages
render CommonMark with raw HTML and automatic image requests disabled; other
transcript fields render as text. Code and output can be copied, with ANSI/OSC
control sequences removed. Source audit and implementation evidence are under
`Research/R4OS/Agent-Sessions/` in the development workspace; architecture and
operating details are documented in `Docs/Agent-Sessions.md` outside this Git repo.

## Rust projects with SDK 0.64.66 (0.3.7)

New Project supports Rust Terminal, Desktop and Service applications using the official SDK creator. Studio reads `r4os-sdk-capabilities` schema 2 through the published compiler-free ModuleCatalog query. SDK support, local tools and Linux execution qualification are separate facts. Other Rust module types retain the SDK's specific rejection reasons. Generated projects include `module.R4MF`, real entry sources, Cargo.toml, Cargo.lock and the SDK build wrappers; no SDK-owned project pin file is created. Studio keeps version selection and immutable project pins in Projects.sqlite.

Under **System → Updates → Tools → Rust**, download and select **1.99.0 · SDK 0.64.66**. This profile contains the published SDK tools, isolated PowerShell 7.6.7, Rust/Cargo 1.99.0, rustup 1.29.1, required LLVM tools and the `x86_64-unknown-none` target. Downloads verify SDK-Release.json, toolset/archive hashes and the SDK's own readiness checks before the installation appears as complete. A missing exact Contract revision is installed as a technical dependency; other defaults are preserved. Generic Rust releases remain independently available. No global PowerShell/rustup/PATH changes or full DevKit installation are required.

The selected SDK source is `41770f2c354e461a5663ad805b7b2955dab1d5a9`. Rust projects pin Contract `50a38becae5765e0f85f6af6713fc72e00583952` from the release manifest, while Zig/C retain SDK's declared `95f762623e6ac2025e9a8aa781713c7c957629a8` Contract dependency. Both report package version 0.64.41; exact revisions and package/archive hashes distinguish them. Rust pins additionally bind compiler/Cargo/linker/sysroot, runner, CPU/codegen and exported tool profile/release identities. Existing projects retain their pins across defaults and SDK updates.

The official scripts require writable host-tool permissions. Studio gives them a hash-checked private copy of the small exported tools under Projects/.studio/tools; shared SDK, Contract and toolchains remain read-only to the web service. Creation validates trusted generated files and never runs a user build script. An explicit local build of a registered project is available to the unprivileged service user:

```sh
python3 scripts/projects/build-rust.py <immutable-project-uuid>
```

The command uses the project's stored roots/pins, the unchanged SDK build driver, isolated cache and offline/locked Cargo dependencies. It does not add a browser build/deploy endpoint. The SDK's source hashes, Cargo.lock and CPU/ABI checks remain mandatory. SDK versions 0.64.61–0.64.65 were never enabled for Studio Rust creation, so no existing Studio Rust wrappers require a `-ProjectPin` migration; caller metadata remains untouched.

Validated: all three Rust artifacts plus all twelve Zig/C combinations with SDK 0.64.66, 23 backend tests, six component and seven updater tests, build/TypeScript and lint. Missing LLVM tools block Rust without blocking Zig/C; changed Contract inputs are rejected and stale success artifacts removed by the SDK driver. SDK runtime qualification covers console/gui/service on Kernel 0.1.381 with the 0.86.39 generation; Studio's generated artifacts were built/inspected locally, not guest-qualified by these host builds. Existing 0.84.47 VM bindings are not a Rust compatibility claim. Sources: [SDK release manifest](https://github.com/R4OSDev/r4os-sdk/releases/download/v0.64.66/SDK-Release.json), [capability interface](https://github.com/R4OSDev/r4os-sdk/blob/41770f2c354e461a5663ad805b7b2955dab1d5a9/Tools/ModuleCatalog/Capabilities.txt). Workspace evidence: Research/R4OS/Projects/Rust/.

## Rust toolchains (0.3.6)

System → Updates → Tools → Rust manages stable Rust toolchains and explicitly loaded older releases. Sources are the official Rust release index and SHA-256-checked immutable channel manifests; each required archive is checked against that manifest. An installation contains rustc, Cargo, the bundled linker, host libraries and the declared `x86_64-unknown-none` target component under `Data/R4OS/Toolchains/Rust/<version>/`. This target is a toolchain profile, not proof of Rust R4OS application support.

The existing unprivileged component service installs verified official component archives into private temporary storage, checks compiler/Cargo identities and a real `no_std` object build, then verifies relocation and publishes the directory atomically. The official installer runs without root in a temporary path without spaces. Saved release metadata, licenses and per-file/component checksums remain with each installation. No global rustup or host PATH changes. Downloads activate nothing; deliberate Use as default updates only the tool selection after integrity checks. Existing project pins and running jobs retain their versions. The matched SDK profile for actual Rust projects was added in 0.3.7 above.

Validated: Rust/Cargo 1.99.1 and 1.99.0, including the older download through the production browser, target libraries/linker and compilation before and after relocation. Latest/older default switching and rejection of an altered compiler were exercised through the same UI with an isolated profile. Five component, seven updater and 22 backend tests, build/TypeScript and lint passed. That 0.3.6 validation left production defaults unchanged. Since 0.3.7, the matched SDK Rust profile can be selected for project creation. Private QA projects and services were removed after validation.

## Projects in the browser (0.3.5)

New Project opens a compact modal with Name, Description, Language, Module type and optional Virtual machine. Subsystem host adds Guest formats. The native dialog manages focus, Escape and background input; narrow layouts stack fields. Rust availability follows the verified SDK capabilities and local tools. A stable request is saved in browser session storage before submission, so an unconfirmed response can be retried after reload without duplicate projects. Request IDs also work on the private HTTP LAN origin.

The first column lists projects after New Project; the second contains Sessions, Editor and Settings. Sessions lists New Session and saved sessions in the third column; Editor keeps it empty. Settings offers General and Virtual machine, with forms in the main area. Name/description and VM assignment can be saved or cancelled; project/tab changes protect unsaved work, and late responses remain bound to the original UUID. Sessions are implemented; editor functionality remains planned.

Verified in the browser through a deliberately lost creation response and reload/retry, Zig/C creation, Settings Save/Cancel, project isolation, tab navigation, modal focus/Escape and layouts down to 320 px. Tests use separate temporary project catalogs, including provider/update fixtures; the production Projects directory is never a test fixture.

## Project creation and Settings API (0.3.4)

The session/CSRF-protected `POST /api/projects` creates a pinned project with a server-generated immutable UUID. A durable SQLite request reserves its identity and inputs, generated files are validated in private staging, synchronized and hashed, then published with Linux `renameat2(RENAME_NOREPLACE)`. Only ready entries appear in the list. Startup and a repeated request resume interrupted work, including publication before the final DB commit. Reusing a request ID with different data is rejected. Changed/foreign files and interrupted staging are retained for review. Completed retries keep the original project identity and pins even if defaults change.

`GET/PATCH /api/projects/:id` reads or updates Name, Description and VM reference with a project revision. Stale saves fail; metadata saves never move the directory or rewrite manifests, technical names or pins. `GET /api/projects/vms` supplies read-only VM choices independently of SDK availability. VM references can be assigned, changed or removed; unavailable references remain visible. Creation/settings never start, stop, deploy to or change a VM. The browser workflow is available since 0.3.5.

## Standalone project templates (0.3.3)

The SDK adapter now generates complete module skeletons: Zig/C Terminal, Desktop, Service, Runtime library and Subsystem host; Zig Driver and Protocol module. Each offered combination is checked with the official parser and a real minimal artifact build for both supported SDK/Contract profiles. This verifies build/container correctness, not guest behavior. Rust templates followed in 0.3.7; pure C driver/protocol templates remain unavailable.

Runtime libraries include the real API contract, baseline, implementation ABI, Zig/C bindings, conformance sources and API documentation generated by the official R4LContractGen. C uses the generated table initializer; ABI layouts are not recreated by Studio. Subsystem projects require actual guest formats. Project build files delegate to the manifest and pin SDK package/revision; exact compiler and Contract pins are returned for the external project catalog. SDK/example license and source attribution are retained.

Creation validates generated files only; it does not execute user build scripts. Project-build/deploy endpoints are still outside this increment.

## SDK manifest adapter and C tools (0.3.2)

The session-bound `GET /api/projects/options` exposes the pinned language/type catalog. Studio builds and caches the official ModuleCatalog as the service user, validates SDK/Contract package hashes with the selected Zig compiler, and consumes its JSON plan and contract plan. Verified profiles currently use SDK 0.64.35/Contract 0.64.20 or SDK 0.64.58/Contract 0.64.41 with Zig 0.16.0; unknown combinations remain unavailable. Rust support for the newer verified release is described in 0.3.7 above. Template generation and the creation API followed in 0.3.3/0.3.4.

System → Updates → Tools → C shows the shared Zig C compiler installation, downloads and default. It delegates to the same Zig inventory and creates no duplicate compiler installation. A real C console skeleton was built and inspected with the active profile.

## Project catalog (0.3.1)

Projects now lists ready entries from `Data/Projects/Projects.sqlite`, using immutable UUIDs and display names. Foreign folders are preserved and are not imported automatically. The bounded Python sqlite3 helper runs as the Studio service user; Node 20 remains supported. The catalog uses schema version 1, full SQLite synchronization and a project revision for Settings changes. Unknown or corrupt databases fail without reinitialization. Creation and Settings were added in 0.3.4/0.3.5.

For managed deployments run `python3 scripts/install-project-support.py` as root once. It grants the web service write access only to the persistent Projects directory and takes effect on the next Studio start; it preserves existing update configuration, SDK/image permissions and VM services. All project data remains excluded from Git. Rolling back preserves the DB and project files; older folder-only releases do not understand the DB catalog.

## Projektverwaltung – Roadmap 0.3.X

Roadmap 14 / 0.3.X: 0.3.1–0.3.7 implementieren Projektkatalog, offizielle Manifestvalidierung, geprüfte Zig-/C-/Rust-Vorlagen, wiederaufnehmbare Create-/Settings-API, Browseroberfläche sowie C-/Rust-Werkzeuge. 0.3.7 hat die gelieferte SDK-/Contract-Unterstützung nach Quellprüfung, tatsächlichen Builds und produktiver Prüfung übernommen. Diese sieben Unterversionen und ihre 25 Aufgaben sind abgeschlossen. Auf Benutzerauftrag ist dieselbe Roadmap ab 0.3.8 um acht Unterversionen/26 Aufgaben für Sessions und Agent-Runs erweitert, insgesamt 51 Aufgaben. 0.3.8–0.3.15 ergänzen Workspace-Ablage, qualifiziertes Codex-Profil, persistente Sessions/Runs, Datei-/Terminalwerkzeuge, Browseroberfläche, Rechte und Wiederherstellung; keine Archivierung oder neue Hauptversion. Editorfunktion und allgemeine Build-/Deploy-Endpunkte bleiben separat geplant.

Studio-Metadaten liegen in `Data/Projects/Projects.sqlite`; Projektquellen unter `Data/Projects/<immutable-uuid>/Workspace/`, Sessiondaten daneben unter `Sessions/`. Ein kleiner fester Python-sqlite3-Adapter erhält Node-20-Kompatibilität. Name/Beschreibung und VM-Zuweisung können geändert werden, ohne UUID, Ordner, technischen Modulnamen, Manifest oder Compiler-/SDK-/Contract-Pins umzuschreiben. Der Browser hält Formular und Navigation; der unprivilegierte Host übernimmt SQLite, Dateierzeugung und offizielle SDK-Werkzeuge. Alle Daten bleiben von Git ausgeschlossen. Gezielte Hosteinrichtung: `scripts/install-project-support.py`.

Die Menüführung lautet Projects/New Project → Sessions, Editor, Settings. Bei Sessions enthält Spalte drei New Session und gespeicherte Sessions; bei Editor bleibt sie leer; unter Settings enthält sie General und Virtual machine. Formulare liegen im Hauptbereich. Drei gleich breite Navigationsspalten und englische UI bleiben erhalten. Das Overlay enthält ausschließlich erforderliche Eingaben und konkrete Status-/Fehlermeldungen.

R4OS-Modularten: R4X mit console/gui/service, R4D, R4P und R4L; Subsystem host ist eine GUI-R4X-Rolle. Verfügbar sind Zig/C für Terminal/Desktop/Service/Runtime library/Subsystem host und Zig für Driver/Protocol module. Alle zwölf Kombinationen wurden mit beiden unterstützten SDK-/Contract-Profilen tatsächlich minimal gebaut. Rust ergänzt seit 0.3.7 die drei nachgewiesenen R4X-Appklassen mit passender Manifest-/Start-/Buildunterstützung; weitere Rust-Rollen bleiben gesperrt.

Geprüfte Profile: SDK 0.64.35 (`2fdc71e11d6a26fd1998dfddb43923f9d707abda`) mit Contract 0.64.20 (`03195b2a2e7461c72a4d0d6b645ae24319ba6315`) oder SDK 0.64.58 (`0508853ba75f4d6e8b7bbe8515fa63ed0d314da1`) mit Contract 0.64.41 (`95f762623e6ac2025e9a8aa781713c7c957629a8`), jeweils Zig 0.16.0. Unbekannte Kombinationen bleiben gesperrt. Der offizielle ModuleCatalog validiert Manifeste und liefert Katalog Schema 4 sowie für R4X App-Plan Schema 1 und den semantischen Contract-Plan. Ein separates Formular-JSON-Schema liegt in diesen Revisionen nicht vor. Aktive SDK-/Contract-/Zig-Standards wurden nicht umgestellt.

Planung und Prüfbelege im übergeordneten Workspace: `Docs/Project-Creation.md`, `Research/R4OS/Projects/Implementation/`. Build-/Containerprüfungen belegen keinen Gastlauf.

## Projects-Navigation (historisch: 0.2.9, außerhalb der Roadmap)

Dieser Abschnitt beschreibt den früheren Ordnerkatalog. Seit 0.3.1 ersetzt ihn SQLite; seit 0.3.5 gelten die oben beschriebenen drei Navigationsebenen.

Im **Projects**-Tab heißt die erste Spalte **Projects** und listet die direkten Projektordner unter `Data/Projects/` alphabetisch mit natürlicher Zahlensortierung auf. Ordnername und Projekt-ID stimmen vorerst überein; pro Projekt liegen Quellen und spätere Build-Ausgaben unter `Data/Projects/<project-id>/`. Dateien und Symlinks werden nicht als Projekte angezeigt. Ohne Projekte erscheint **No projects yet.**; die bisherigen Platzhalter Workspace, Example Project sowie deren Components und Views entfallen. Die zweite und dritte Spalte behalten ihre Breite und bleiben ohne Überschrift und Inhalt. Eine Auswahl zeigt zunächst nur den Projektnamen im Hauptbereich.

Der Browser lädt die Liste beim Öffnen des Tabs über das ausschließlich lesende `GET /api/projects`. Der Host listet nur fertige registrierte SQLite-Projekte; Host/Origin-Prüfung und `Cache-Control: no-store` schützen den Zugriff. Fehlender Speicher ergibt eine leere Liste, andere Lesefehler eine eigene Fehlermeldung. Im verwalteten Deployment wird `Projects/` neben dem bereits konfigurierten `STUDIO_R4OS_DIR` aufgelöst, sodass alle Releases denselben vorhandenen `App/Data/Projects/`-Speicher verwenden. Es entstehen keine Projektkopien im Release-Verzeichnis; `Data/` bleibt vollständig ignoriert. Projektanlage, Settings und Sessions sind implementiert; Editor und allgemeine Build-/Deploy-Endpunkte bleiben geplant.

Geprüft: 21 Backendtests, Produktionsbuild/TypeScript und Lint. Im Browser leere und gefüllte Projektliste aus echten isolierten Ordnern, Ausschluss von Dateien/Symlinks/Unterordnern, Sortierung, erhaltene Auswahl beim Tabwechsel, unveränderte System-Navigation und gesonderte Fehleranzeige. Desktop, 390 und 320 px ohne horizontales Überlaufen; drei gleich breite Spalten. Lokale Belege im Workspace unter `Research/R4OS/Projects/`.

## Codex-Standard in bestehenden Deployments (0.2.8)

Die vom alten Host-Installer gesetzte CODEX_BINARY-Vorgabe blockiert die verwaltete Standardwahl nicht mehr. Neue Provider-Prozesse lösen den ausgewählten, geprüften Codex-Pfad auf; bestehende Clients bleiben bestehen. Abweichende explizite Administrator-Pfade und injizierte Test-Clients behalten ihre Vorgabe. Die Regression für Legacy-Dienstvariable und eigenen Override wird im bestehenden Werkzeugtest geprüft. Echte isolierte Account-Clients mit der Legacy-Dienstvariable starten nach Standardwahl mit Codex 0.163.0 beziehungsweise 0.162.1; der erste Client bleibt bei erneutem Standardwechsel bestehen. Danach Standards zurückgestellt und QA-Provider entfernt. Ausschließlich account/read, ohne Login-Anfrage, Modellaufruf oder Zugriff auf bestehende Konten. Build/Lint und 20 Backendtests bestanden.

## VM-Releasewechsel ab 0.2.7

Settings bietet **R4OS Release** aus allen vollständig importierten lokalen Full-Abbildern desselben Updates-Inventars. Ein Wechsel ist eine eigene Aktion bei gestoppter VM mit Warnung und ausdrücklicher Bestätigung für diese VM und das bisherige/neue Release. Er verwirft alle Änderungen auf **C: und D:** und erhält das **Exchange Drive**, UUID, Name, CPU/RAM und Network. Cancel, dieselbe Release-Auswahl, Wiederholungen und gewöhnliches Save settings löschen keine Daten; veraltete Bestätigungen werden abgewiesen. Offenen Gastabgleich zuerst abschließen, Konflikte blockieren den Vorgang. Globale Standards ändern weiterhin keine vorhandenen VM-Bindungen.

Der Host verifiziert das Zielabbild erneut, erzeugt ein frisches privates Overlay und tauscht die vollständige Instanz samt Konfiguration mit Linux `renameat2(RENAME_EXCHANGE)` atomar aus. Austauschabbild, Share, Synczustand, Konfliktkopien und Logs bleiben über Hardlinks erhalten. Eine persistente Transaktion unter Instances ermöglicht die Wiederherstellung vor/nach dem Commit; das Systemabbild wird nicht rebased. Python 3 und Linux mit atomarem Directory Exchange sind dafür Hostvoraussetzungen. Fehler vor dem Commit erhalten den alten veröffentlichten Zustand; ein bereits erfolgter Commit wird erkannt und bei Wiederholung nicht erneut ausgeführt.

Real im unprivilegierten Dienst/Browser mit eigener QA-VM geprüft: C:/D:-Dateien zuerst über Neustarts erhalten, bestätigter Wechsel **0.84.47 → 0.84.46**, beide Dateien anschließend im Gast nicht mehr vorhanden, F:-Datei unverändert lesbar. Exchange-Abbild, Share und Synczustand behielten beim Wechsel ihre Inodes und SHA-256; UUID, übrige Einstellungen und Network blieben erhalten. Warnung/Cancel, gewöhnliches Speichern, gleiche Auswahl, aktive Settings-Sperren und Livekonsole bis 320 px geprüft. 20 Backendtests einschließlich beschädigtem Zielabbild, veralteter Bestätigung, Retry und beiden Wiederaufnahmezuständen, drei Komponenten-/sieben Updater-Tests, Build/TypeScript und Lint bestanden. Belege im Workspace: `Research/R4OS/Components/VM-Release-*.json`.

## VM-Netzwerk ab 0.2.6

Settings enthält **Network**, je VM dauerhaft gespeichert und seit 0.3.55 für neue VMs standardmäßig aktiviert. Bestehende Werte bleiben erhalten; bestehende Konfigurationen ohne Feld bleiben deaktiviert. Änderungen nur bei gestoppter VM, wirksam ab dem nächsten Start; Overview zeigt Enabled/Disabled. QEMU verwendet bei Aktivierung eine RTL8139-Karte mit stabiler lokaler MAC und SLIRP-NAT/DHCP ohne Portweiterleitungen. Bei Deaktivierung weiterhin `-nic none`. Keine Bridge, keine Gastdienste im LAN/VPN. Gastbereitschaft wird nicht aus dem QEMU-Prozessstatus abgeleitet. Grundlage: [QEMU user networking](https://www.qemu.org/docs/master/system/devices/net.html).

Bestehende Hosts einmal explizit als root mit `python3 scripts/install-vm-network.py` erweitern. Der Installer ergänzt ausschließlich die Socket-Familien im VM-Template per Drop-in und schreibt eine feste Capability-Datei; Dispatcher, Datenpfade und laufende VMs bleiben erhalten. Neue Hosteinrichtungen rufen ihn über `install-vm-support.sh` auf. Ohne diese Unterstützung bleibt das Einschalten gesperrt und wird verständlich angezeigt. Kein allgemeines sudo und keine automatische Root-Ausführung durch Updates.

19 Backendtests einschließlich Legacy-Vorgabe, fehlender Hostfähigkeit, boolescher Eingabe, Persistenz und Erhalt bei gewöhnlichen Settings-Saves sowie Build/TypeScript und Lint bestanden. Checkbox, Save/Reload und Overview-Anzeige im echten Browser geprüft. Echter Gastnachweis: DHCP 10.0.2.15, bidirektionale SSH-Verbindung über ausschließlich temporäre Loopback-Testweiterleitung, Abschalten ohne Netzwerkkarte beim nächsten Start und erneutes Einschalten. Full 0.84.47 benötigt RTL8139 (in 0.2.7 korrigiert, e1000 aus 0.2.6 ist dort nicht verwendbar). Testweiterleitung entfernt. Belege im Workspace unter `Research/R4OS/Components/`.

## VM-Oberfläche ab 0.2.5

Overview und Console teilen denselben beständigen VM-Kopfbereich außerhalb der View-Karte und ihres Scrollbereichs. Status links, Aktionsgruppe zentriert mit Icons in der Reihenfolge **Start, Restart, Shutdown, Force Stop**. In Settings, Exchange und Logs ist die Leiste ausgeblendet; Restart/Force Stop behalten ihre Bestätigung. Die Console zeigt den Betriebsstatus nur im Kopf-Badge. Screen Controls sind zentriert; unter dem Display folgen zentrierte Sondertasten und danach der Maus-/Escape-Hinweis ohne Keyboard-Layout-Text. Verbindungsfehler bleiben sichtbar. Build/TypeScript und Lint bestanden; Browserprüfung aller fünf Views, beständiger Kopf beim Wechsel, Zentrierung/Icons/Reihenfolge und Layout bis 320 px sowie Health HTTP 200 bestanden.

## Komponentenverwaltung ab 0.2.1 / Releases ab 0.2.4

**R4OS Releases ab 0.2.4:** Neueste und ältere stabile Full-x86_64-Abbilder stammen aus den offiziellen Distribution-Releases. Archiv-Prüfsumme, Release-Manifest und entpacktes Disk-Abbild werden vor atomarer Veröffentlichung geprüft; Lizenzen und Quellmetadaten bleiben erhalten. Die Update-Seite und VM-Verwaltung verwenden dasselbe lokale Images-Inventar. Der Import läuft vollständig unprivilegiert; das Zielverzeichnis wird erst nach der atomaren Veröffentlichung schreibgeschützt. Downloads aktivieren keinen Standard. Der explizit ausgewählte globale Standard bestimmt neue VMs; bestehende VM-Imagebindungen bleiben unverändert. Bei fehlendem/ungültigem Standard im vorhandenen Profil ist die Erstellung gesperrt, bis ein lokales Release gewählt wurde. API und Formular binden die angezeigte Image-ID.

QEMU-Korrektur in 0.2.4: Der Source-Build läuft im privaten temporären Verzeichnis ohne Leerzeichen. Anschließend wird die Installation auf dem Daten-Dateisystem atomar veröffentlicht. Damit funktionieren Datenpfade wie `R4OS Studio`; die bisher aktive QEMU-Version bleibt bei Buildfehlern erhalten. Heruntergeladene Quellen werden weiterhin vor dem Build signaturgeprüft.

**Tools ab 0.2.3:** Zig-Versionen stammen aus dem offiziellen Downloadindex und werden gegen dessen SHA-256 und ihre Versionsausgabe geprüft. Codex bietet ausschließlich die aktuellste stabile offizielle Linux-x86_64-Version zum Download; Archiv-Digest, CLI-Version, generiertes Account-Protokoll und App-Server-Initialisierung werden mit leerem, isoliertem `CODEX_HOME` geprüft, ohne Anmeldung oder Modellaufrufe. Vorhandene ältere Codex-Versionen bleiben als Standard auswählbar; ein Wechsel gilt für neue Provider-Kindprozesse und erhält bestehende Anmeldedaten/Prozesse. Der CLI-Pfad wird bei jedem neuen Prozess aus dem Standardprofil aufgelöst, mit festem zulässigem Pfad und Binär-Prüfsumme. Ein abweichendes `CODEX_BINARY` bleibt ein Administrator-Override. Seit 0.2.8 wird die vom alten Installer gesetzte Vorgabe `/opt/r4os-studio/bin/codex` als bisheriger Fallback behandelt und folgt ebenfalls der gewählten Standardversion; neue Dienstvorlagen setzen diese Legacy-Variable nicht mehr. Grundlage: [offizielle App-Server-Dokumentation](https://learn.chatgpt.com/docs/app-server).

QEMU wird für parallele neuere/ältere Versionen aus dem offiziellen Source-Archiv gebaut. Vor dem Entpacken die Release-Signatur gegen den fest gebundenen Schlüssel `CEACC9E15534EBABB82D3FA03353C9CEF108B584` prüfen. Der Build läuft unprivilegiert, ohne automatische Downloads von Build-Abhängigkeiten, mit VNC/PNG und SLIRP; er stellt QEMU und qemu-img gemeinsam bereit und hält deren Binär-Prüfsummen fest. Originalarchiv, Signatur, öffentlicher Schlüssel und Lizenzen liegen beim installierten Tool unter Sources. Der absolute, für diesen Build unbenutzte EDK2-X11-Hilfslink wird beim sicheren Entpacken ausgelassen; die Originalquelle bleibt vollständig erhalten. Erforderliche Debian-Hostpakete vorab explizit installieren: `build-essential pkg-config libglib2.0-dev libpixman-1-dev libslirp-dev ninja-build meson python3-venv python3-wheel libfdt-dev libgnutls28-dev zlib1g-dev libpng-dev gnupg`. Der Host-Installer begrenzt den Komponenten-Dienst auf acht CPU-Kerne und 8 GiB RAM; neue Unit-Einstellungen nach expliziter Wartung bei inaktivem Auftrag mit `systemctl restart r4os-studio-components` übernehmen.

Neue VM-Prozesse verwenden den gewählten QEMU-Standard; das konkrete Werkzeug wird zusätzlich zur Worker-Release in der privaten Runtime festgehalten. Laufende VMs behalten ihren Prozess und ihr Werkzeug. Vorhandene Systemwerkzeuge bleiben erhalten. Neue Standardprofile übernehmen zuerst die vorhandenen Minimalprofil-Pins und bestehenden Systemwerkzeuge, ohne neuere bereitliegende Versionen automatisch zu aktivieren. Libraries werden erst auf ausdrückliche Auswahl zum Standard.

Real geprüft: Zig 0.17.0 und ältere Version, Codex 0.163.0 mit Account-Schema/isolierter Initialisierung, signierter QEMU-11.1.2-Build und älterer QEMU-11.1.1-Download/Build. R4OS Full 0.84.47 bootet mit QEMU 11.1.2 bis zum Desktop; PNG-Diagnose geprüft. 19 Backendtests einschließlich Werkzeugpfad-/Prüfsummenprüfung, drei Komponentenprüfungen, sieben Updater-Tests, Build/TypeScript und Lint bestanden. Belege im übergeordneten Workspace unter `Research/R4OS/Components/`.

System → Updates trennt **R4OS Studio**, **Components** (SDK, Contract, Libraries), **Tools** (Zig, QEMU, Codex) und **R4OS Releases**. Die führenden dekorativen Vierecke in der Components-Spalte wurden anwendungsweit entfernt. Studio-Updates bleiben separat.

Die gemeinsame Komponentenverwaltung inventarisiert vorhandene Installationen, erhält parallele Versionen und speichert globale Standards unter `Data/R4OS/Profiles/versions.json`. Download und Aktivierung sind getrennte Aktionen. Ein SDK-Standardwechsel wählt den exakt passenden installierten Contract und Compiler gemeinsam. Projekt-Pins und VM-Imagebindungen bleiben erhalten; Projektüberschreibungen folgen mit der Projektintegration.

Ab 0.2.2 liefern **SDK**, **Contract** und **Libraries** ihre tatsächlichen offiziellen Versionskataloge. Diese Repositories besitzen derzeit keine Versions-Tags; Studio liest die Paketversionen aus `build.zig.zon` des aktuellen main-Commits und dessen Versionshistorie. Jede Auswahl ist an eine vollständige Commit-ID gebunden. **Load older versions** erweitert den Katalog; gleich benannte, vom SDK exakt gebundene Contract-Revisionen werden zusätzlich berücksichtigt. Git nutzt ausschließlich die festen öffentlichen GitHub-Repositories mit normaler TLS-Prüfung und ohne Credentials. Archive werden an dieser Commit-ID bezogen, ihre Paketmetadaten gegen Git verglichen, Archiv-SHA-256 und tatsächlicher Zig-Pakethash aufgezeichnet; Contract-Pakethashes zusätzlich gegen die SDK-Vorgabe geprüft. Vorhandene Installationen werden nicht überschrieben. Compiler-Prüfungen verwenden die benötigte bereits installierte Zig-Version. Libraries bleiben optional. Tools und R4OS-Abbilder sind ebenfalls angebunden.

Für 0.2.2 real unprivilegiert geprüft: SDK 0.64.58 an `0508853ba75f4d6e8b7bbe8515fa63ed0d314da1`, Contract 0.64.41 an `95f762623e6ac2025e9a8aa781713c7c957629a8`, Libraries 0.64.23; zusätzlich älteres SDK heruntergeladen und Katalog über zehn Stände erweitert. Die unveränderte Example-App aus dem bisherigen Minimalnachweis baut mit dem neuen SDK/Contract-Paar und Zig 0.16.0 erfolgreich: 9/9 Schritte, R4M0 inspect OK. Das ist ein Buildnachweis, keine Bestätigung der Laufzeitkompatibilität mit dem alten Full 0.84.47. Bisherige aktive Profile wurden durch Downloads nicht umgestellt. 18 Backendtests, zwei Komponentenprüfungen, Produktionsbuild/TypeScript und Lint bestanden.

Explizite Hostwartung nach Bereitstellung dieser Release: `python3 scripts/components/install.py` als root ausführen. Der Installer erhält die bestehende Update-Konfiguration und installiert einen festen Launcher sowie den unprivilegierten Dienst `r4os-studio-components.service`. Private Unix-Schnittstelle mit Peer-UID-Prüfung; ausschließlich Status/Prüfung/Download/Standardwahl für feste Komponententypen und Versionsidentitäten. Die Browser-API prüft zusätzlich Sitzung, CSRF und Host/Origin. Der Webdienst erhält keine freie Shell-/URL-Schnittstelle oder Schreibrechte auf SDKs/Images. Der Komponenten-Dienst darf gezielt Komponenten/Profile schreiben; Provider-, Projekt- und VM-Instanzdaten sind in seinem Sandbox-Namensraum gesperrt. Er folgt neuen Studio-Releases zwischen Aufträgen; laufende Aufträge verwenden ihren ursprünglichen Code. Keine VM wird neu gestartet.

Prüfung: 18 Backendtests, sieben Host-Updater-Tests, zwei gezielte Komponentenprofil-/Quellenprüfungen, Produktionsbuild/TypeScript und ESLint bestanden. Browsernavigation, Inventar/Standardauswahl, gleiche Navigationsbreiten bis 320 px und Health HTTP 200 geprüft. Lokale Belege im übergeordneten Workspace: `Research/R4OS/Components/`.

Lokales Grundgerüst einer browserbasierten Entwicklungsumgebung für R4OS.

## Repository

Dieses Verzeichnis ist das lokale Git-Repository. Remote: `https://github.com/R4OSDev/r4os-studio.git`, Branch `main`. Jede fertiggestellte Unterversion wird committed und gepusht. Aus dem übergeordneten Workspace unter Linux: `./Tools/Push.sh "Kurze Commit-Beschreibung"`; unter Windows: `Tools\Push.bat "Kurze Commit-Beschreibung"`.

`Data/` wird beim Start beziehungsweise bei der Dienstinstallation angelegt und gehört einschließlich aller Unterordner nicht ins Repository. Leere ignorierte Ordner werden von Git nicht übertragen.

`AGENTS.md` und `Tools/` liegen im übergeordneten Workspace und werden nicht in dieses Repository aufgenommen. Das öffentliche Hauptrepository ist `R4OSDev/r4os-studio` auf GitHub; `origin` zeigt dorthin. Normale HTTPS-Zertifikatsprüfung bleibt aktiv. GitHub ist die einzige aktive Git- und Update-Quelle; der frühere Gitea-Remote und seine speziellen Zertifikats-/IP-Einstellungen sind entfernt. Push-Zugangsdaten liegen ausschließlich in den lokalen Tools außerhalb dieses Repositories. Remote-URLs und anonyme Updates enthalten keine Zugangsdaten.

Im übergeordneten Workspace liegen außerdem separate Quellcode-Checkouts unter `Research/Codex/`, `Research/OpenClaw/` und `Research/OpenCode/`. Herkunft und genaue Revisionen stehen in `Research/sources.json`. Der Codex-Checkout enthält die öffentlichen CLI-/SDK-/App-Server-Komponenten; ein öffentliches Repository für die vollständige Desktop-Oberfläche wurde nicht bestätigt. Diese Quellen dienen der Recherche und sind keine installierten App-Abhängigkeiten oder Bestandteil dieses GitHub-Repositories.

## Starten

Voraussetzungen: Node.js 20 ab 20.19, 22 ab 22.13 oder ab Version 24, außerdem Corepack (alternativ pnpm 10.18.3 direkt installieren). Für neue Installationen Node.js 24 LTS verwenden.

```bash
cd App
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

Frontend: <http://127.0.0.1:5173> · Backend: <http://127.0.0.1:3001/api/health>

`dev` startet beide Prozesse; Strg+C beendet sie gemeinsam. Einzeln starten: `corepack pnpm dev:frontend` bzw. `corepack pnpm dev:backend`. Die Ports 5173 und 3001 müssen frei sein. `PORT` kann den Backend-Port ändern; dann auch das Proxy-Ziel in `frontend/vite.config.ts` anpassen.

## Enthalten

- Purple/Dark-Design mit dunkelvioletten Flächen, lavendelfarbener Schrift und violetten Akzenten für Auswahl, Tabs und Tastaturfokus. Favicon und Browser-Theme-Farbe sind darauf abgestimmt.
- Vollständig englische Benutzeroberfläche, einschließlich zugänglicher Beschriftungen und Browser-Metadaten (`lang="en"`). Neue UI-Texte werden auf Englisch ergänzt.
- Obere Tab-Leiste mit **System** und **Projects**, ohne Workspace-Kennung rechts. Auch mit Pfeiltasten, Pos1 und Ende bedienbar.
- Links drei gleich breite Navigationsspalten: im System-Tab **Areas → Components → Views**, im Projects-Tab **Projects → Sessions / Editor / Settings → Sessions / Files / Settings-Unterpunkte**; Editor zeigt den Files-Baum und rechts die volle Codefläche. Keine Zähler, wiederholten Kontextüberschriften oder Management-Fußnoten. Ihre Breite entspricht auf dem Desktop der bisherigen dritten Spalte; der übrige Platz steht dem Hauptbereich zur Verfügung.
- Im Tab **System** gibt es **Settings → LLM Provider**, **Virtual Machines** und **Updates → R4OS Studio**. **New Provider** steht in **Views** immer zuerst, darunter stehen die gespeicherten Provider ohne Nummerierung. Verbundene OpenAI-Abonnements zeigen rechts im Provider-Button den verbleibenden Quotenanteil.
- Im Tab **Projects** steht **New Project** vor dem SQLite-Projektkatalog. Die Einträge zeigen Anzeigenamen und bleiben über unveränderliche UUIDs mit ihren Ordnern unter `Data/Projects/` verbunden.
- Rechts ein Hauptbereich mit Seitentitel und Inhalt, ohne Breadcrumb-Navigation oder zusätzliche Kontextüberschrift über dem Seitentitel.
- Die untere Leiste zeigt **R4OS Studio** horizontal mittig und **Version …** rechtsbündig. Die Versionsnummer stammt aus `shared/version.json`.
- Die Auswahl bleibt pro Tab im Speicher erhalten; Neuladen setzt sie zurück.
- Auf schmalen Bildschirmen stehen die drei Navigationsspalten oberhalb des Hauptbereichs.
- Ein Fastify-Backend mit `GET /api/health`. Der Status beschreibt ausschließlich den Studio-Server, keine R4OS-Instanz.

Projektanlage, Browser-Editor, Sessions mit Agent-Runs, isolierte Projekt-Build-/Deploy-/Run-Aufträge, OpenAI-Provider- und unabhängige VM-Verwaltung sind implementiert. Die Oberfläche lädt keine externen Schriftarten oder anderen Medien.

## OpenAI mit ChatGPT-Abonnement

1. **System → Settings → LLM Provider → New Provider** öffnen.
2. **OpenAI** auswählen, einen Anzeigenamen vergeben und **Add OpenAI provider** anklicken.
3. Im gespeicherten Provider **Continue with ChatGPT** anklicken. R4OS Studio zeigt einen einmaligen Code.
4. **Open OpenAI sign-in** öffnet die offizielle OpenAI-Anmeldung in einem eigenen Tab. Dort anmelden und den Code bestätigen.
5. R4OS Studio erkennt den Abschluss automatisch und zeigt Konto, Plan und **Connected**. Die Verbindung bleibt nach einem Dienstneustart gespeichert.

Es wird kein API-Key benötigt. Die Zugangsmöglichkeiten hängen vom ChatGPT-Konto und dessen Codex-Berechtigungen ab. Der Provider kann lokal getrennt und erneut verbunden oder vollständig entfernt werden. **Disconnect** und **Remove** beenden zugehörige Agent-Runs vor dem Löschen lokaler Zugangsdaten; eine globale Abmeldung oder bestätigte Remote-Widerrufung wird nicht behauptet. Bestehende Codex-CLI-Anmeldungen bleiben getrennt. Projektbezogene Chat-/Inference-Aufträge laufen über die Sessions-API.

Die Anmeldung verwendet ausschließlich die Account-RPCs des offiziellen Codex-App-Servers, keine nachgebauten OpenAI-OAuth-Endpunkte oder kopierten Client-IDs. Getestete Binary: **codex-cli 0.162.1**. Der Dienst-Installer kopiert die vorhandene eigenständige CLI-Binary nach `/opt/r4os-studio/bin/codex`; auf neuen Hosts vorher die offizielle eigenständige Codex CLI installieren. Für die Entwicklung lässt sich deren Pfad über `CODEX_BINARY` setzen. `STUDIO_DATA_DIR` bestimmt direkt das Provider-Datenverzeichnis; ohne Vorgabe wird `App/Data/LLMProvider/` verwendet. Diese Vorgabe gilt für Entwicklung und Produktion. Die Anwendung ist für den privaten LAN-/VPN-Betrieb eingerichtet. Für öffentliche oder kommerziell gehostete Angebote ist der reguläre, von OpenAI freigegebene **Sign in with ChatGPT**-Web-Client erforderlich; der aktuelle Device-Code-Adapter ist dafür nicht vorgesehen.

Jeder Provider hat einen eigenen geschützten Server-Speicher. Das lokale Verzeichnis `Data/LLMProvider/` erhält Modus `0700`; Metadaten liegen atomar geschrieben mit `0600` in `providers.json`. Die jeweiligen Codex-Anmeldedaten liegen in UUID-Unterordnern. `/Data/` und sämtliche Unterordner sind durch `.gitignore` ausgeschlossen. Beide Push-Skripte beachten diese Regeln und brechen zusätzlich ab, falls Data-Dateien bereits versioniert sind oder die Ausschlussregel fehlt. Auth-Tokens verbleiben im jeweiligen Codex-Speicher auf dem Server. Der Browser erhält ausschließlich öffentliche Konto-, Quoten- und Reset-Metadaten sowie während seines eigenen Login-Vorgangs den kurzlebigen Benutzer-Code. `HttpOnly`-/`SameSite=Strict`-Cookies binden Login-Vorgänge an die Browser-Sitzung; Änderungen benötigen zusätzlich einen CSRF-Token. Es gibt keine Mehrbenutzerkonten oder Rollen: Provider-Verwaltung gehört zum gemeinsamen, vertrauenswürdigen Studio-Workspace im LAN/VPN. Für weitere Hostnamen `STUDIO_ALLOWED_HOSTS` als kommagetrennte Liste setzen; standardmäßig werden lokale Interface-Adressen, localhost und der Rechnername akzeptiert. TLS ist für den Betrieb außerhalb dieser vertrauenswürdigen Netze erforderlich.

Die Analyse der drei Referenzprojekte und die genaue Herkunft stehen im Workspace unter `Docs/OpenAI-Subscription.md` und `Research/sources.json`.

## Usage limits und verfügbare Resets

Einen verbundenen OpenAI-Provider auswählen. **Usage limits** zeigt alle von OpenAI gemeldeten Quoten mit verbrauchtem und verbleibendem Anteil, Fensterdauer und nächstem Reset. Absolute Zeitpunkte enthalten die Browser-Zeitzone; zusätzlich steht die verbleibende Zeit dabei. Es werden nur tatsächlich gemeldete Fenster angezeigt, ohne eine feste Annahme über Tages- oder Wochenlimits. Fehlende Werte heißen **Not reported**. Ein vergangener Reset-Zeitpunkt setzt die Anzeige nicht automatisch auf frei: Erst eine neue Antwort von OpenAI bestimmt den aktuellen Stand.

Die Provider-Buttons in **Views** zeigen rechts den niedrigsten bekannten verbleibenden Prozentsatz über alle gemeldeten Quotenfenster und Buckets. Beispielsweise ergeben 80 % im kurzen und 25 % im langen Fenster eine Anzeige von **25%**. Nicht verfügbare Werte erscheinen als **—**, niemals als erfundene 0 % oder 100 %. Der Tooltip erklärt die Zusammenfassung; die einzelnen Fenster stehen weiterhin in der Detailansicht. Die Werte werden für verbundene Abonnements bereits ohne Auswahl des Providers beim Öffnen der Provider-Navigation geladen und bei sichtbarer Navigation minütlich aktualisiert. Aktualisierungen aus der Detailansicht und bestätigte Reset-Ergebnisse fließen direkt in die Button-Anzeige ein. Beim Kontowechsel beziehungsweise Neuladen der Provider-Liste werden bisherige Prozentwerte verworfen.

Die Ansicht lädt beim Öffnen, danach ungefähr einmal pro Minute bei sichtbarer Seite und über **Refresh usage**. Der Server hält erfolgreiche Werte maximal 15 Sekunden im Arbeitsspeicher pro Provider; manuelles Aktualisieren umgeht diesen Cache. Bei einem Fehler bleiben zuvor geladene Werte als möglicherweise veraltet gekennzeichnet.

**Available resets** zeigt die gemeldete Gesamtzahl zusätzlicher Reset-Guthaben sowie verfügbare Titel, Status, Vergabe- und Ablaufzeiten. Die Anzahl bleibt maßgeblich, falls OpenAI nur einen Teil der Einzelheiten liefert. Nicht gemeldete Verfügbarkeit wird nicht als null verfügbare Resets dargestellt. Diese Guthaben sind unabhängig von den normalen zeitgesteuerten Quoten-Resets.

**Use a reset** öffnet zunächst eine Bestätigung. Erst **Confirm reset** sendet den Verbrauch an OpenAI. OpenAI wählt standardmäßig das nächste verfügbare Guthaben und entscheidet, welche Fenster zurückgesetzt werden können. Studio aktualisiert danach die Quoten anhand einer neuen Abfrage. Es gibt keine automatische Nutzung von Reset-Guthaben, keine Käufe und keine Modellaufrufe.

Jeder logische Einlöseversuch hat eine UUID als Idempotenzschlüssel. Der Browser speichert ihn vor dem Senden im Sitzungsspeicher, damit ein unklarer Ausgang auch nach Navigation oder Neuladen mit derselben ID erneut geprüft werden kann. **Retry previous reset** / **Retry same reset** verwenden diese ID weiter. Die Ablage enthält ausschließlich die Anfrage-ID und ihren Sendestatus, keine Auth-Tokens. Ein bestätigter Verbrauch mit anschließend fehlgeschlagener Quotenabfrage wird als bestätigtes Ergebnis angezeigt; die Quoten können separat nachgeladen werden. Der Sitzungsspeicher gilt für den jeweiligen Browser-Tab.

- `GET /api/providers/:id/usage`: lesende Abfrage; optional `?refresh=true`.
- `POST /api/providers/:id/usage/resets`: ausschließlich für ausdrücklich bestätigtes Einlösen mit Sitzung, CSRF-Token, `confirm: true` und `idempotencyKey`. Optional kann ein bekanntes `creditId` übergeben werden; die Oberfläche überlässt die Auswahl OpenAI.

Die Umsetzung verwendet die offiziellen Account-RPCs `account/rateLimits/read` und `account/rateLimitResetCredit/consume`. Herkunft und Protokollgrenzen sind unter `Docs/OpenAI-Subscription.md` dokumentiert. Verbrauchende Tests verwenden ausschließlich kontrollierte Fake-Clients. Die bestehende persönliche Verbindung wurde nur lesend geprüft; kein echtes Reset-Guthaben wurde eingelöst.

## Versionsnummer

Die maßgebliche App-Version steht ausschließlich in `shared/version.json` im Format `major.minor.patch`. Für eine neue Unterversion diese Datei anpassen. Das Frontend liest sie direkt für die untere Leiste; das Backend verwendet dieselbe Version für die Codex-Client-Metadaten.

`node scripts/sync-version.mjs` überträgt die Version in die Paketmetadaten von `package.json`. `corepack pnpm build` führt diesen Schritt automatisch vor dem Bauen aus. `package.json` deshalb nicht unabhängig versionieren. `shared/version.json` gehört auch beim Produktionsstart zur Anwendung und muss zusammen mit den Build-Dateien vorhanden sein.

## Aufbau und Entscheidungen

```text
App/
├── frontend/src/
│   ├── app/                         Layout, Navigation, gemeinsame Icons und Styles
│   ├── features/llm-providers/       Provider-Oberfläche, API-Client und React-Zustand
│   │   └── components/              NewProvider, ProviderDetails, ProviderPanel, Usage-Ansichten
│   └── main.tsx                     Browser-Einstieg
├── backend/src/
│   ├── app.ts                       HTTP-App zusammenstellen und konfigurieren
│   ├── server.ts                    Prozessstart und Beenden
│   └── modules/llm-providers/
│       ├── routes.ts                HTTP-Routen und Eingabevalidierung
│       ├── sessions.ts              Browser-Sitzungen, Origin-/Host-Prüfung und CSRF
│       ├── service.ts               Provider- und Login-Lebenszyklus
│       ├── store.ts                 Persistenz und private Provider-Verzeichnisse
│       ├── errors.ts                HTTP-Fehler des Moduls
│       └── openai/                  Codex-Prozess und Usage-/Reset-Adapter
├── backend/test/                    Isolierte Provider-Integrationstests
├── shared/
│   ├── llm-providers.d.ts            Öffentliche Datenverträge, keine Zugangstokens
│   └── version.json                 Maßgebliche App-Versionsnummer
├── Data/LLMProvider/                Lokale Laufzeitdaten; vollständig ignoriert
├── scripts/                         Gemeinsamer Entwicklungsstart
└── pnpm-lock.yaml                   Aufgelöste Abhängigkeitsversionen
```

React und TypeScript strukturieren die interaktive Studio-Oberfläche. Vite übernimmt Entwicklungsserver und Frontend-Build. Fastify stellt die lokale HTTP-API bereit; `@fastify/static` liefert beim Produktionsstart das gebaute Frontend über denselben Ursprung aus. ESLint prüft TypeScript und die React-Hook-Regeln. Die genaue Paketauflösung steht im Lockfile.

Browser: Layout, Navigation, Provider-Verwaltung und Anmeldecode. Der Feature-API-Client ist von React getrennt; `useProviders.ts` verwaltet den React-Zustand. Server: Health-Endpunkt, Provider-API, isolierte Codex-Kindprozesse, Persistenz und statische Frontend-Dateien. Ausschließlich `frontend/dist/` wird statisch ausgeliefert; `Data/` ist über HTTP nicht zugänglich. Im Entwicklungsbetrieb leitet Vite `/api` zum Backend weiter; dadurch ist keine zusätzliche CORS-Freigabe nötig. Die Entwicklungsserver binden an `127.0.0.1`. Im Produktionsbetrieb liefert ein gemeinsamer Server Frontend und API über `0.0.0.0:5010` aus. `HOST` und `PORT` überschreiben die jeweiligen Vorgaben.

Projektpersistenz, Manifestvalidierung und eigenständige Projektgerüste sind implementiert; die unabhängige VM-Verwaltung besitzt einen eigenen Runner. Agent Sessions, Browser-Editor und isolierte Projekt-Build-/Deploy-/Run-Aufträge sind ebenfalls implementiert; versioniertes API-Wissen bleibt ein späterer Umfang. Zig, SDK und Contract werden zur Projekterstellung bereits geprüft und gebunden; die Vorlagen wurden isoliert minimal gebaut.

## R4OS: einzelne Apps statt Gesamtworkspace

Entscheidung vom 18.10.2026: Studio lädt und baut das ausgewählte App-Projekt. Ein vollständiger R4OS-Workspace ist keine Voraussetzung.

| Fähigkeit | Benötigte Komponenten |
|---|---|
| App bauen | App-Quellen/Manifest/Build-Dateien, Zig 0.16.0, `r4os-sdk` und dessen gebundener `r4os-contract`. |
| Zusätzliche Bibliothek verwenden | Nur bei App-Bedarf die passenden Library-Bindings/-Verträge; zur Laufzeit passende R4L-Module im Gast. |
| App in R4OS ausführen | Optional: geprüftes R4OS-Binärabbild, QEMU und ein noch zu integrierender Deploy-/Test-Runner. |
| API-Wissen anzeigen | Passende Contract-/SDK-Referenzen und ausgewählte Dokumentation; kein zusätzlicher Build-Schritt. |

**Praktisch geprüft:** Die unveränderte offizielle [Example-App](https://github.com/R4OSDev/r4os-app-example/blob/bf1d27058a54d0998eabe1d32f6fb05ab47796c5/build.zig) wurde temporär auf diesem Linux-Host mit ausschließlich Compiler, SDK und Contract zu `EXAMPLE.R4X` gebaut. Exitcode 0, **9/9 Schritte erfolgreich**, einschließlich `R4M0 inspect OK`. Keine Libraries, Kernel-, Distribution-, Project- oder DevKit-Quellen waren dafür erforderlich. Zig wurde über den [DevKit-Checksum-Pin](https://github.com/R4OSDev/r4os-devkit/blob/d362a4c20a651338cec678d6c177063ebfb12cb2/Setup/Setup.ps1) geprüft; Linux-Archiv-SHA-256: `70e49664a74374b48b51e6f3fdfbf437f6395d42509050588bd49abe52ba3d00`. Die SDK-/Contract-Archive stimmen mit den deklarierten Zig-Pakethashes überein.

Geprüfte Build-Revisionen:

- Example: `bf1d27058a54d0998eabe1d32f6fb05ab47796c5`.
- SDK `0.64.35`: `2fdc71e11d6a26fd1998dfddb43923f9d707abda`.
- Contract `0.64.20`: `03195b2a2e7461c72a4d0d6b645ae24319ba6315`.
- Zig `0.16.0`.

Aus dem App-Verzeichnis mit absoluten Pfaden zu diesen entpackten Paketen und zum geprüften Compiler:

```sh
"$ZIG" build --prefix "$OUTPUT" --fork="$SDK" --fork="$CONTRACT" --summary all
```

Das [App-Paket](https://github.com/R4OSDev/r4os-app-example/blob/bf1d27058a54d0998eabe1d32f6fb05ab47796c5/build.zig.zon) bindet SDK, [SDK wiederum Contract](https://github.com/R4OSDev/r4os-sdk/blob/2fdc71e11d6a26fd1998dfddb43923f9d707abda/build.zig.zon). Die beim Build verwendeten lokalen `--fork`-Verzeichnisse müssen ihre tatsächlichen Revisionen bewahren; der deklarierte Archivhash prüft keine beliebig geänderten lokalen Quellen. Der Linux-App-Wrapper kann mit angepassten `Settings.R4S`-Pfaden direkt Zig starten; PowerShell und der vollständige DevKit-Installer sind für diesen Pfad nicht nötig.

`module.R4MF` v2 ist die maßgebliche App-Beschreibung für Identität, Modulversion, Quellen, Einstieg, Imports, Ressourcen und Installationsziel. `build.zig.zon` hält zusätzlich Paketabhängigkeiten fest. Notepad und Calculator verwenden denselben grundlegenden SDK-Pfad. [Clock](https://github.com/R4OSDev/r4os-app-clock/blob/8a56eef6570c20a2d9fdcb43c2c56bed0dc1a9c6/build.zig) benötigt dagegen R4STD-Bindings und bindet Libraries an `20507b4504345e8ddc399735efdbaedca8776d5d`. Das vorhandene Libraries-Paket ist ein Repository-Archiv; separat veröffentlichte Binding-Pakete sind nicht bestätigt. Es wird bei Bedarf geladen, ohne alle Bibliotheken zu bauen.

**Versionen:** Der untersuchte SDK-Hauptzweig `d62062c0a8f1d1d9fc3c5ac0d228d719c51669a2` (`0.64.37`) bindet bereits Contract `6d2feb313aa8892e8a3df7cb7f2e9545e4544362` (`0.64.21`). Dieses Paar ersetzt die App-Pins nicht automatisch. Das zukünftige Projektprofil bindet Compiler/Prüfsumme, SDK/Contract samt Pakethashes, optionale Libraries und Testabbild/Hash gemeinsam.

**Tests:** Ein veröffentlichtes [Full-Abbild 0.84.47](https://github.com/R4OSDev/r4os-distribution/releases/tag/v0.84.47) ist ein Kandidat für GUI-Tests. ZIP-SHA-256: `cee402a6a6ae5130389ae0f367fa6ce7702aad91a4534f23f70919398dc628b4`. Sein geprüftes Quellmanifest nennt SDK `66c0ec3eeac8bf940f29afd515a7c6eba4aab61d`, Contract `03195b2a2e7461c72a4d0d6b645ae24319ba6315` und Libraries `4f2087cc114582878845b7ed69776f5b31c5a88d`. Bei der ursprünglichen SDK-Untersuchung wurde das Image noch nicht gebootet. Inzwischen ist genau dieses Release für die unabhängige VM-Verwaltung importiert und getestet; siehe Virtual Machines. R4X läuft im R4OS-Gast, nicht als Linux-Programm oder direkt im Browser.

Der Deploy-Pfad muss noch mit offiziellen Werkzeugen/Formaten nachgewiesen werden. Upstream besitzt R4UPack und ImageCreator in `r4os-distribution`; diese Untersuchung bestätigt noch keinen vollständigen App-Deploy in ein vorhandenes Image. Keine pauschale Abhängigkeit vom Distribution-Gesamtbuild einführen. Die unabhängige VM-Verwaltung verwendet inzwischen private Overlays des Basisabbilds ohne Gastnetzwerk; keine Gastdienste für LAN/VPN oder Internet freigeben.

Zuständigkeiten: Projektbedienung, Formulare und Navigation im Browser; Projektpersistenz, Dateierzeugung und offizieller SDK-Adapter in getrennten unprivilegierten Backend-Helfern. Compiler und VM benötigen Hostausführung. Die Projektmodule sind implementiert, Editor und allgemeiner Projekt-Build-/Deploy-Runner bleiben geplant; die VM-Verwaltung besitzt einen eigenen Runner. Projekte benötigen die gezielte Hosteinrichtung aus dem Abschnitt Project catalog.

Die vollständige Quellen-/Abhängigkeitsprüfung und alle untersuchten Hauptzweig-Revisionen stehen im übergeordneten Workspace unter [`Docs/R4OS-Components.md`](../Docs/R4OS-Components.md). Der erste Nachweis erfolgte temporär; das anschließend lokal installierte Setup ist im folgenden Abschnitt beschrieben.

## Installiertes R4OS-Minimalsetup

```text
Data/
├── R4OS/
│   ├── Toolchains/Zig/0.16.0/
│   ├── Toolchains/Rust/<version>/
│   ├── SDK/2fdc71e11d6a26fd1998dfddb43923f9d707abda/
│   ├── Contract/03195b2a2e7461c72a4d0d6b645ae24319ba6315/
│   ├── Libraries/<revision>/
│   ├── Images/<image-id>/
│   ├── Instances/<uuid>/
│   └── Profiles/minimal.json
├── Projects/
│   ├── Projects.sqlite
│   ├── .studio/                   private Arbeits-/Werkzeugablage
│   └── <uuid>/                    Projektquellen und Build-Ausgaben
└── LLMProvider/                   bestehende Provider-Daten
```

Die versionierte Profilvorlage [`shared/r4os/minimal-profile.json`](shared/r4os/minimal-profile.json) bindet Zig 0.16.0, SDK 0.64.35 und Contract 0.64.20 mit Quell-URLs, Archiv-SHA-256 und SDK-/Contract-Zig-Pakethashes. Die installierte Profilkopie unter `Data/R4OS/Profiles/minimal.json` verwendet relative Pfade zum R4OS-Ordner. Dieses Minimalprofil enthält ausschließlich die Build-Werkzeuge; QEMU und Full-Abbild sind inzwischen separat für die VM-Verwaltung eingerichtet. Weitere Libraries und Werkzeuge sind über Updates separat verwaltet; Projekte laden zusätzliche Bindings nur bei konkretem Bedarf.

Das Setup benötigt Linux x86_64 und Python ab 3.12. Aus dem App-Verzeichnis als Besitzer von `Data/`:

```sh
python3 scripts/setup-r4os.py
```

Auf diesem Host gehört `Data/` dem Dienstbenutzer; deshalb aus dem Workspace-Stamm als root `runuser -u r4os-studio -- python3 App/scripts/setup-r4os.py` ausführen. Das Skript lädt nur die drei gebundenen Archive, prüft SHA-256 vor sicherem Entpacken, ersetzt keine vorhandenen Installationen und veröffentlicht das Profil nach Prüfung von Zig-Version und beiden Pakethashes. Wiederholte Aufrufe verwenden vorhandene Installationen ohne Download. Optional `--archive-dir /absolute/path` mit geprüften Archiven namens `zig.tar`, `sdk.tar`, `contract.tar`; die Dateiendung legt die Komprimierung nicht fest.

Aus einem passenden App-Projekt mit absoluten Pfaden zum installierten Profil bauen:

```sh
R4OS_ROOT='/Data/Projekte/R4OS Studio/App/Data/R4OS'
"$R4OS_ROOT/Toolchains/Zig/0.16.0/zig" build \
  --prefix "$PWD/Artifacts" \
  "--fork=$R4OS_ROOT/SDK/2fdc71e11d6a26fd1998dfddb43923f9d707abda" \
  "--fork=$R4OS_ROOT/Contract/03195b2a2e7461c72a4d0d6b645ae24319ba6315" \
  --summary all
```

Die Installation wurde als `r4os-studio` geprüft: Zig-Version und Pakethashes stimmen, ein erneuter Setup-Lauf verwendet vorhandene Komponenten, und ein frischer Example-Build mit den installierten Pfaden besteht alle 9 Schritte einschließlich R4M0-Prüfung. Protokoll und Ergebnis liegen unter `Data/R4OS/Profiles/minimal-build.log` und `minimal-verification.json`; das temporäre Prüfprojekt wurde entfernt. Ein VM-Test fand nicht statt.

SDK/Contract/Compiler werden projektübergreifend genutzt; eigene App-Quellen und Ausgaben gehören unter `Data/Projects/`. `Data/` bleibt vollständig ignoriert, auch für beide Push-Skripte. Der Setup läuft außerhalb der systemd-Isolierung als unprivilegierter Benutzer. Die Toolchain-Bereitstellung enthält noch keinen Projekt-Build-Endpunkt. Die gesonderte VM-Verwaltung erweitert gezielt die Schreibrechte für Instanzen und deren Runtime. Ausführliche Einrichtung und Rechte: [`../Docs/R4OS-Setup.md`](../Docs/R4OS-Setup.md). Die reine Toolchain-Bereitstellung änderte die WebApp nicht; die spätere VM-Verwaltung ist in Version 0.1.13 enthalten.

## Virtual Machines

Unter **System → Virtual Machines** steht **+ New VM** in Components; darunter die gespeicherten VMs. Views: Overview, Console, Settings, Exchange, Logs. VMs sind unabhängig von Projekten und können parallel laufen. Projekte können eine optionale VM-ID referenzieren; diese Zuweisung verändert oder startet keine VM.

- Neue VMs verwenden das neueste vollständige lokale Full-Release nach numerischer Versionsnummer und starten ausgeschaltet. Das importierte Image bleibt unverändert; jede UUID unter `Data/R4OS/Instances/` hat ihr eigenes vollständiges QCOW2-Overlay. Die vorhandenen C:/D:-Partitionen bleiben erhalten.
- Name, CPU und RAM sind bei gestoppter VM änderbar. Start, Restart, Shutdown und Force Stop (Restart/Force Stop bestätigt) und bestätigtes Delete sind implementiert. Ein eigener systemd-Dienst pro VM erhält laufende Gäste über Studio-Neustarts hinweg. VMs starten nach einem Host-Reboot zunächst ausgeschaltet. Shut down sendet eine ACPI-Anfrage; deren Abschluss ist für den getesteten Gast noch nicht bestätigt. Force stop wurde erfolgreich geprüft.
- `Instances/<uuid>/Exchange/Share/` nimmt fertige Artefakte auf. Seit 0.1.14 wird ein dauerhaftes, vom Gast beschreibbares FAT32-Abbild mit Label **R4SHARE** über USB eingebunden. Gaständerungen einschließlich Löschungen werden nach QEMU-Ende über `ExecStopPost` des VM-Dienstes in den Hostordner zurückübertragen, auch ohne laufenden Studio-Webdienst. Beim geprüften R4OS Full 0.84.47 erscheint er als **F:**; die Buchstabenvergabe erfolgt im Gast. Hoständerungen werden beim nächsten Start übernommen; ohne Hoständerungen bleibt das vorhandene Abbild bestehen. Offene Gastabgleiche werden vor jedem Start wiederaufgenommen, bevor ein Abbild erneuert werden darf.
- Die direkte QEMU-Option `fat:32:` erzeugte im Test einen ungültigen FAT32-Aufbau und wurde verworfen. Der implementierte Generator verwendet `mkfs.fat`/`mcopy`, einen MBR und eine FAT32-Partition. Der Host-Ordner ist kein live synchronisiertes Dateisystem.
- `Exchange/state.json` speichert SHA-256-Basisstände und den Syncstatus. Gleichzeitige abweichende Änderungen derselben Datei blockieren einen neuen Start; beide Fassungen bleiben unter `Exchange/Conflicts/<session>/Guest/` und `Host/` mit `conflicts.json` erhalten. Gewünschte Gastfassung nach `Share/` übernehmen (bei Gastlöschung dort entfernen), dann **Retry exchange sync**. Eine andere Hostfassung separat sichern und nach erfolgreichem Abgleich erneut einsetzen.
- Abgleichfehler lassen das Image unverändert erhalten und werden in Exchange angezeigt. Unterordner, ungültige Namen und überschrittene Dateigrenzen verhindern den Export; Image separat wiederherstellen, keine automatische FAT-Reparatur. Force stop kann ungespeicherte Daten verlieren oder FAT beschädigen.
- Exchange erlaubt zunächst gewöhnliche Dateien mit ASCII-Namen, keine Unterordner oder Symlinks: 128 Dateien, insgesamt 96 MiB, Browser-Upload maximal 8 MiB je Datei. Upload/Remove/Settings werden im laufenden Betrieb gesperrt.
- Console überträgt ab 0.1.15 das Gastbild laufend mit noVNC. Fit/Actual size, Fullscreen, Screenshot, View only, Reconnect und Sondertasten sind implementiert. Klick/Capture mouse fängt die relative Maus für Klicks und Ziehen; Escape gibt sie frei und beendet Vollbild. Native Tastaturereignisse unterstützen gehaltene Tasten; US-Gastbelegung. Onscreen-Kombinationen werden gehalten gesendet. Sehr kurze synthetische Modifier-Taps in Sofort-Textmakros waren im Gasttest nicht zuverlässig; eine Paste-Funktion ist nicht implementiert. Pointer Lock benötigt einen Desktopbrowser; Touch, Scrollrad, Gast-Clipboard und Audio sind noch nicht angebunden. Logs zeigt begrenzte serielle Gast-/QEMU-Ausgaben. Gastnetzwerke sind standardmäßig deaktiviert und je VM als privates NAT aktivierbar; VNC und QMP verwenden ausschließlich lokale Unix-Sockets. Display und Maus benötigen getrennte, CSRF-geschützt erzeugte 20-Sekunden-Einmaltickets, Browser-Sitzung und passenden Origin. Tickets sind auf VM, Sitzung und Kanal gebunden und werden im WebSocket-Unterprotokoll statt in URLs übertragen. Zwei Displays und ein Mauscontroller je VM; Backpressure, Rate-/Nutzdatenlimits und Heartbeats begrenzen Verbindungen. Maustasten werden auch bei Transportverlust gelöst.

Datenstruktur:

```text
Data/R4OS/
├── Images/<image-id>/image.json, disk.img, release/
└── Instances/<vm-uuid>/
    ├── vm.json
    ├── Disks/disk.qcow2, exchange.img
    ├── Exchange/Share/
    ├── Exchange/state.json
    ├── Exchange/Conflicts/<session>/Guest/, Host/, conflicts.json
    └── Logs/qemu.log, serial.log
```

Hosteinrichtung aus dem Workspace-Stamm als root:

```sh
apt-get install --no-install-recommends qemu-system-x86 qemu-utils dosfstools mtools
./Tools/install-vm-support.sh
./Tools/install-service.sh
python3 App/scripts/import-r4os-image.py --version 0.84.47
```

Der Image-Importer prüft die offizielle ZIP-Prüfsumme und anschließend Größe/SHA-256 des entpackten Disk-Abbilds gegen das Release-Manifest, entpackt Sparse-Nullbereiche und erhält Lizenzen/Quellenmetadaten. Vorhandene Images werden nie überschrieben. Ohne `--version` wird das neueste stabile Full-Release importiert; optional ein vorhandenes ZIP über `--archive /absolute/path` verwenden. Python ab 3.11 erforderlich. Die installierte QEMU-Version auf diesem Host ist 10.0.13; das importierte Full-Release 0.84.47 ist geprüft und bootfähig. Es wurden keine weiteren R4OS-Repositories installiert.

Die Livekonsole benötigt noVNC 1.7.0 (Decoder, Tastatur, Skalierung), @fastify/websocket 11.3.4 (Fastify-Hooks) und ws 8.22.0 (rückstaufähiger Stream); diese Versionen sind im Lockfile gebunden. Der Decoder wird nur beim Öffnen einer laufenden Konsole geladen. Frontendlogik: `Console.tsx` und `usePointer.ts`; Hosttransport/Eingabe: `console.ts` und `pointer.ts`. Relative Bewegungen werden für den PS/2-Gast in kleine, zeitlich verteilte Pakete zerlegt. Ein frei wählbarer QMP-Befehl ist nicht über den Mauskanal verfügbar. Quellen/Bedienung: [noVNC API](https://github.com/novnc/noVNC/blob/v1.7.0/docs/API.md) und [`../Docs/VirtualMachines.md`](../Docs/VirtualMachines.md).

Die Module liegen unter `frontend/src/features/virtual-machines/`, `backend/src/modules/virtual-machines/` und `shared/virtual-machines.d.ts`. Metadaten und lokale Dateien bleiben unter dem ignorierten `Data/`. Die WebApp darf gezielt `Data/R4OS/Instances/` und die VM-Runtime beschreiben; Images und Toolchains bleiben im Dienst schreibgeschützt. Polkit erlaubt dem unprivilegierten Dienstbenutzer nur Start/Stop gültiger UUID-Instanzen der festen VM-Vorlage. VM-HTTP-Anfragen sind über Sitzung, Host-/Origin-Prüfung und CSRF geschützt.

Geprüft: zwei parallele VMs mit getrennten Austauschdateien und unveränderten VM-Dienst-PIDs nach Studio-Neustart; Uploads auf laufende VMs abgewiesen. Im Gasttest waren C: und D: sowie F: mit lesbarer `PROBE.TXT` vorhanden. Browseranlage, Datei-Upload, Start, Konsole und gleich breite Spalten bis 320 Pixel sind geprüft. Fünfzehn Backendtests, ESLint und Build bestehen. Seit 0.1.14 im echten Full-0.84.47-Gast zusätzlich geprüft: Dateien auf F: anlegen, lesen, löschen und ändern; Erhalt über einen zweiten Gaststart, Hostimport und Rückübertragung bei gestopptem Webdienst. Konfliktanzeige und Retry nach manueller Auflösung sind im Browser geprüft. Zwei reguläre netzlose VM-Dienste liefen parallel mit laut QMP beschreibbaren Austauschdatenträgern; Stoppen einer VM ließ die andere aktiv und beide Stopps synchronisierten erfolgreich. Die vorhandene Beispiel-VM wurde unter Erhalt von STUDIO.TXT migriert. Ein isolierter Sparse-Importtest prüft Disk-Hashes, Metadaten/Lizenzen und den Schutz bestehender Images. Livekonsole 0.1.15 zusätzlich mit Full 0.84.47 geprüft: Maus-Doppelklick/Fensterziehen, gehaltene Tastaturmodifikatoren, Mausfreigabe beim Studio-Neustart unter Erhalt des VM-PID, Fit/native Pixel, Fullscreen/Escape, PNG-Download in Gastauflösung, View only ohne gesendete Eingaben, Reconnect sowie 390-/320-Pixel-Ansichten. Handshake-Schutz gegen falschen/fehlenden Origin, fremde Sitzung/VM/Kanal und Ticket-Replay live bestätigt. Details und Quellen: [`../Docs/VirtualMachines.md`](../Docs/VirtualMachines.md).

## Prüfen und bauen

```bash
corepack pnpm typecheck
corepack pnpm lint
corepack pnpm test
corepack pnpm build
corepack pnpm start
```

`build` prüft TypeScript und erzeugt `frontend/dist/` sowie `backend/dist/`. `start` stellt die gebaute Anwendung auf Port **5010** für LAN und VPN bereit, lokal unter <http://127.0.0.1:5010>. Der systemd-Dienst und die Skripte in [`../Tools/`](../Tools/README.md) übernehmen den dauerhaften Betrieb. Ein laufender Dienst belegt Port 5010; für einen parallelen manuellen Test einen anderen `PORT` setzen. Die Entwicklungsports 5173/3001 bleiben davon unabhängig.

Das Studio selbst hat noch keine Benutzeranmeldung oder Mehrbenutzerrollen. Die OpenAI-Kontoanmeldung erfolgt separat wie oben beschrieben. Die vorhandene Host-Firewall begrenzt den Zugriff auf die erlaubten Netze; der Installer ergänzt nur TCP 5010 auf dem VPN-Interface `sdwan0`. Eine öffentliche Freigabe ist nicht eingerichtet. R4OS-VMs laufen in gesonderten Diensten, standardmäßig ohne Netzwerk; privates NAT ist je VM ausdrücklich aktivierbar.

Die Backendtests verwenden isolierte temporäre Daten und einen kontrollierten Auth-Client. Sie prüfen Login-Besitz, Kontentrennung, Persistenz, CSRF/Origin/Host-Schutz, OpenAI-only-Validierung, Abbruch, Ablauf, Quoten-Cache und Kontentrennung, fehlende Nutzungsdaten, Reset-Bestätigung und Idempotenz sowie Fehler ohne Token-Leaks. Sie melden keinen simulierten Login als echten OpenAI-Test an. Zusätzlich wurden mit der offiziellen Binary Initialisierung, ein abgemeldetes isoliertes Konto sowie eine echte Device-Code-Anfrage mit anschließendem Abbruch geprüft. Eine vollständige persönliche Anmeldung muss der Benutzer selbst bei OpenAI abschließen.

Bei UI-Änderungen beide Tabs, alle drei Navigationsebenen, Tastatursteuerung und schmale Ansichten im Browser prüfen; `/api/health` muss HTTP 200 liefern. Unbekannte API-Pfade müssen HTTP 404 liefern.

## Studio updates (0.1.17)

**System → Updates → R4OS Studio** zeigt die aktive und neueste veröffentlichte Version, Prüfzeiten, Fortschritt und die letzten zehn Installationen. Prüfung beim Start des Update-Dienstes und danach alle sechs Stunden; **Check for updates** prüft zusätzlich. Ausschließlich **Install update** installiert, niemals der Timer. Die Seite verbindet sich nach dem Studio-Neustart erneut und lädt neue Frontend-Dateien. Versionen werden über stabile Tags `vMAJOR.MINOR.PATCH` veröffentlicht; gewöhnliche main-Commits, Vorabversionen und ältere Versionen werden nicht automatisch installiert. Ein Tag muss zur kanonischen `shared/version.json` passen; veröffentlichte Tags nicht verschieben.

Die Implementierung liegt unter `frontend/src/features/updates/`, `backend/src/modules/updates/`, `shared/updates.d.ts` und `scripts/updates/`. Es gibt keine zusätzliche App-Abhängigkeit. Linux/systemd, Python 3, Git, Node und Corepack sind Hostvoraussetzungen. Der bisherige Studio-Dienst/Benutzer und für Provider die eigenständige Codex-Binary bleiben erforderlich. Einmalige Einrichtung nach `corepack pnpm install --frozen-lockfile && corepack pnpm build`:

```bash
sudo python3 scripts/updates/install.py
```

Seit 0.1.18 ist das öffentliche GitHub-Repository `https://github.com/R4OSDev/r4os-studio.git` Standard für neue Installationen und die aktive Update-Quelle dieses Hosts. GitHub-Downloads und Versionsprüfungen benötigen keinen Token; sie verwenden die normalen System-CAs ohne Gitea-CA oder interne Resolver-Zuordnung. Der GitHub-Push-Token bleibt ausschließlich in den privaten Workspace-Tools. Repository-/TLS-Konfiguration liegt unter `/etc/r4os-studio-updates/config.json`; die Browser-API akzeptiert keine URLs oder Kommandos. Bei Migration bestehender Gitea-Installationen dort `repository` ändern, `caFile` und `resolve` entfernen und nur den Koordinator neu starten. Branch main sowie die unveränderten Tags v0.1.15, v0.1.16 und v0.1.17 wurden übernommen; neue Releases weiterhin separat taggen. Für andere private Git-Hosts bleiben `--repository`, `--ca-file` und `--resolve` explizite Administratoroptionen; TLS-Prüfung nicht deaktivieren.

Der versionierte Bootstrap enthält die benötigten neuen Dienstdefinitionen und Launcher ohne Zugangsdaten. Der Workspace-Wrapper `../Tools/install-update-support.sh` ruft denselben Installer auf. Er schützt eine vorhandene Konfiguration vor versehentlicher Neuinitialisierung. Für frische Hosts ohne VM-Unterstützung ist `scripts/install-vm-support.sh` ebenfalls versioniert; erst Emulator/FAT-Werkzeuge installieren. Ein bereits eingerichteter VM-Dienst wird beim Bootstrap ohne VM-Neustart auf den Dispatcher umgestellt.

- `r4os-studio-updates.service`: eigener Host-Koordinator, startet automatisch. Enger Unix-Socket mit Peer-UID-Prüfung unter `/run/r4os-studio-updates/`, keine TCP-API. Web-Endpunkte benötigen erlaubten Host/Origin, Sitzung und CSRF. Verwaltung gehört wie Provider/VMs zum vertrauenswürdigen gemeinsamen LAN/VPN-Workspace, ohne zusätzliche Benutzerrollen.
- `r4os-studio-update-build.service`: nur bei Button-Installation, unter separatem Benutzer `r4os-studio-updater`, ohne Privilegien und mit ausschließlich beschreibbarem Build-Cache. Keine Provider-/VM-Daten lesbar. `pnpm@10.18.3`, Lockdatei, Build vor Aktivierung; heruntergeladene Installationsskripte werden niemals als root ausgeführt.
- `/opt/r4os-studio/releases/<version>-<commit>/`: unveränderliche Programmstände. `/opt/r4os-studio/current` wird atomar gewechselt; der Launcher löst den Pfad einmal auf. Version und Release-ID müssen im Health-Endpunkt übereinstimmen; Startfehler lösen Rückrollen aus, auch nach Erreichen des systemd-Startlimits. Persistente Transaktion ermöglicht Wiederherstellung nach unterbrochener Aktivierung.
- **App/Data bleibt am bisherigen Ort**, samt Rechten und Inhalten. Explizite Datenpfade verbinden jede Version mit demselben Provider-/R4OS-Speicher. Updates überschreiben weder den lokalen App-Git-Checkout noch Daten. Nicht committete Quellcodeänderungen blockieren die Installation. Mindestens 1 GiB freier Platz je Staging-/Release-Dateisystem erforderlich.
- Jede VM hält die bei ihrem Start ausgewählte Release unter `worker.json` in ihrer Runtime fest. Start und `ExecStopPost` verwenden denselben Worker. Der Updater startet ausschließlich den Studio-Webdienst neu; laufende VM-Prozesse bleiben aktiv. Alte Releases werden deshalb nicht automatisch gelöscht. VM-Neustarts verwenden die dann aktive Version. Basisimages, SDK/Contract und QEMU werden nicht durch Studio-Updates aktualisiert.
- `shared/update-host.json` bindet Host-Protokoll, Datenschema und VM-Worker-Protokoll an Version 1. Inkompatible Releases werden abgewiesen und benötigen explizite Host-/Datenwartung. Es gibt derzeit keine automatische Datenmigration, Betriebssystem-Paketinstallation oder Aktualisierung des privilegierten Bootstrap-Codes. Die Anwendungsfreigabe darf solche Änderungen nicht stillschweigend voraussetzen.

Root-Status/Transaktion und Verlauf: `/var/lib/r4os-studio-updates/`. Privater Build-Cache: `/var/cache/r4os-studio-updates/`. Diagnose: `journalctl -u r4os-studio-updates -u r4os-studio-update-build -u r4os-studio`. Für Entwicklung weiterhin den App-Checkout mit `pnpm dev` nutzen; ein einfaches Bauen des Checkouts ändert die aktive unveränderliche Release nicht. `Tools/start.sh`, `stop.sh` und `restart.sh` steuern weiterhin ausschließlich den Webdienst. Host-Reboot lässt VMs wie bisher ausgeschaltet.

Prüfen: `corepack pnpm build`, `corepack pnpm lint`, `corepack pnpm test` sowie `python3 scripts/updates/test_host.py`. Python-Tests simulieren Aktivierung/Fehlstart/unterbrochene Wiederherstellung, prüfen Dateninhalte/Inodes und verhindern echte Host-Kommandos. Backend-Tests prüfen Sitzung, CSRF, Origin/Host, feste Release-Eingaben und nicht konfigurierte Host-Unterstützung.

### Agent sessions (0.3.10)

Projects store session metadata and replayable events in `Sessions/Sessions.sqlite`,
with native Codex conversation state in `Sessions/<session-id>/Codex/`. Project
sources live in `Workspace/`. The browser/API never receives provider credentials.
Run admission is idempotent by request UUID and freezes settings and project pins;
one run may use a project at a time, with two active runs per host. Native Codex
0.163.0 is qualified by binary hash; unsupported binaries fail closed.

The host requires Linux/systemd, Bubblewrap and the existing `r4os-studio` user.
After installing a release, explicitly provision its fixed unprivileged services:
`sudo python3 /opt/r4os-studio/current/scripts/agent-sessions/install.py`.
This preserves the existing bootstrap and running VMs. The coordinator communicates
through a private Unix socket. Each run has its own bounded systemd unit and pinned
release; closing the browser or restarting Studio does not stop it. Stop interrupts
the native turn and cleans the run unit. Unconfirmed outcomes remain visible and
are never automatically resubmitted. Provider disconnect stops its runs first.

Session/create/settings/history and run/start/stop/event endpoints reuse Projects
sessions, CSRF and Host/Origin checks. SSE resumes using persisted event IDs.
A browser session UI and actual project tool handlers follow in later subversions.
Nine dynamic tool declarations are stable across native conversation resume;
permissions are enforced before each host call. Native shell, patch, web search,
plugins, skills and project instruction discovery are disabled in this profile.

0.3.11 implements the six file tools in a separate Bubblewrap namespace: bounded
UTF-8 reads, directory listing, literal search, atomic file writes, directories
and patches through the qualified Codex patch parser. Only `Workspace/` is
writable; selected SDK/Contract/compiler roots are read-only. Provider credentials,
session state, other projects and VM instances are absent. File writes require
the SHA-256 of the version read; Studio serializes file calls. A failed multi-file
patch may leave partial edits, which its result reports; unconfirmed calls are
never replayed. External administrator/terminal edits are not an atomic compare
and swap transaction with these file tools.

On this host, `ProtectKernelTunables` prevents rootless Bubblewrap's private proc
mount and `RestrictSUIDSGID` filters `open_tree`. The agent installer omits those
two incompatible systemd filters; empty capabilities, NoNewPrivileges, read-only
host mounts and the inner mount/PID/network namespaces enforce execution scope.

0.3.12 adds run-owned terminal tools with pipes or PTY, input/EOF, output polling,
explicit termination and real exit/signal/timeout states. Handles are opaque and
expire with the run. Up to four concurrent processes and 32 handles per run;
default command timeout two minutes, maximum ten. Output is bounded and marked
when clipped. Commands run without network in their own PID namespace, with only
the project workspace writable and pinned components readable. A private run
cache supplies checked offline SDK packages; it contains no conversation/auth
state. Terminal processes also produce durable live transcript items. Run end,
Stop, process timeout and worker-unit cgroup termination clean their descendants.
The user Stop action remains available independently of tool permissions.

For Zig/C, `zig build` uses the pinned `/zig` compiler and checked offline SDK
packages. Rust projects additionally expose their pinned installation at `/rust`
and a private checked tools copy at `/tools`; call the official build driver with
explicit `/sdk`, `/contract`, `/tools`, `/rust/Install`, `/cache` and workspace
output roots. Shared SDK/toolchain files stay read-only. No general deploy or
R4OS guest execution API is implied by terminal support.

0.3.13 adds Projects → Sessions → New Session / saved sessions. A native modal
selects name, connected provider, model and reasoning effort without inference.
The main pane shows a paginated durable conversation, streamed answers, collapsible
file/terminal tool arguments/results and a composer with Stop. Closing a view does
not stop its worker. Session links restore selection on reload; drafts and uncertain
submissions retain the original request ID in browser session storage. A retry
therefore resolves the same run, including a lost start response. SSE reconnects
from its last stored sequence and refreshes browser authentication after a Studio
restart. All transcript content renders as text, without executing model HTML.
Session settings and tool toggles follow in 0.3.14; Editor remains unimplemented.

0.3.14 exposes Session settings from the session header: General selects name,
provider, model and reasoning; Tools provides nine independent switches, initially
on. Save uses the stored revision and is rejected during that session's active
run. Cancel leaves persisted settings untouched; stale/error reload is explicit
and never silently resets disabled permissions. Each new run freezes the saved
rights and checks them before every call, including resumed native conversations.
Known dynamic declarations remain stable because Codex restores them with its
native thread; an advertised disabled tool still receives a host denial and causes
no execution. Explicit provider/model changes use that connected provider's
nonsecret model metadata and original credential store while preserving native
conversation state. Codex binary/profile pins are unchanged by settings edits.


0.3.16 supplies read-only public Unix identity records in the tool namespace so
isolated PowerShell/.NET and the official Rust build driver can start. The
credential/session/VM isolation and network policy are unchanged. Rust R4X builds
were verified with explicit pinned SDK/Contract/tools/install/cache/output roots.
Terminal text limits count its encoded JSON representation, including control
bytes; history pages also have a byte budget so long source/tool transcripts stay
loadable through the bounded helper. Existing schema/protocols and pins remain 1.

Release validation completed through 0.3.16: all nine real dynamic tools, saved
permission denial/re-enable, native context continuation, pinned Zig/C/Rust R4X
builds, parallel projects and same-workspace exclusion. A live worker retained
its PID and old release through a real Studio update. Web/coordinator restart,
SSE reauthentication without duplicate messages, user Stop, queued startup without
inference, corrupt-history preservation and SIGKILL after an effect but before
its receipt were exercised. Explicit recovery did not repeat the command.
The full 25-test backend suite and an additional provider-disconnect race case,
focused agent tests, Python/namespace/recovery/update checks, build, TypeScript
and lint passed. Temporary QA projects, sessions, worker bindings and scratch trees
were removed; shared components/defaults, provider stores and VM instances remain.
The existing OpenAI Main provider returned HTTP 401 and needs sign-in; OpenAI Work
was used successfully. No host reboot, guest execution or deploy capability is
claimed by these agent tests. Roadmap 14 / 0.3.X retains all 51 completed tasks.

0.3.17 completes the requirement-by-requirement roadmap audit: CommonMark/code
transcripts use pinned `react-markdown` 10.1.0 (needed for the planned Markdown/code
view); raw HTML and automatic message-image requests are disabled. Copy actions
for code, arguments and results support the HTTP LAN through a user-gesture
clipboard fallback. Display/copy removes ANSI/OSC control sequences. Source:
https://github.com/remarkjs/react-markdown .

Unsaved Session settings are guarded on close, Escape, navigation and browser
reload; explicit Cancel discards the draft without changing saved values. Tools
contains the required short reminder that terminal commands can change workspace
files. Paginated/truncated file and search results, skipped files and possible
partial patch changes are carried through to their tool cards.

Tool admission now observes the durable stopping state in the same transaction
as its intent, including the interval before SIGTERM delivery. Unconfirmed
mutating I/O results stop the run as unknown, preserve possible effects and close
further admission; they cannot silently continue with another automatic call.
A lost turn/start RPC reply is reconciled with native started/completed events,
without resubmitting the turn or reporting a false timeout after confirmed end.

Validation for 0.3.17: all 28 backend tests passed, with focused Python tests for
durable Stop, uncertain I/O, lost start replies, pagination, official patch
partial changes and interactive terminals. Build/TypeScript and lint passed.
The installed bundle passed copy/HTML/ANSI, settings dirty-guard and 320 px checks
using controlled API fixtures. Real native runs separately verified file-page
metadata, terminal output, browser Copy, context after worker restart and Stop
of a running process with no remaining cgroup. The temporary project, session,
three runs and worker bindings were removed; existing data and defaults remain.
The requirement-by-requirement audit and evidence are retained in
Research/R4OS/Agent-Sessions/Completion-Audit.json in the development workspace.

### Exchange deployment contract

New offline Exchange imports reserve `STXCHG.JSN` for a journaled VM/volume identity. Exchange reset renews the generation; image/system reset keeps it. Guest target discovery uses exact marker bytes across fixed SFTP drive candidates, never a hardcoded F: or volume serial. The immutable VM worker pinned at boot determines recursive Exchange support. Existing deployments remain historical records. Native headless desktop launch still needs a public R4OS launch/initialization contract; SSH alone does not provide it. See `shared/exchange-host.json` and the development contracts. No guest runtime validation was performed for this change.

Exchange sync schema 2 stores files and empty directories under `Build`, with 128 files/96 MiB, 128 directories and six path levels across the whole disk. Metadata and interrupted uploads count toward those limits. All traversals are bounded; extraction has an OS file-size limit. Conflicts preserve both host and guest trees. Publication exchanges two complete directories atomically with a durable inode journal, so recovery never repeats a completed exchange. Existing schema 1 baselines remain readable. Older workers cannot interpret schema 2 and must preserve/block it; restart a running VM normally with the new worker before nested guest uploads. Never change its pinned worker or edit `exchange.img` live. The browser displays the last offline host copy and permits stopped-VM uploads and individual file/empty-folder removal.

New deployment format `exchange-build-v1` uses a verified guest drive and `Build/P<7hex>/D<7hex>`. OWNER and DEPLOY receipts bind full project/deployment UUIDs and Exchange generation. PACKAGE is published last after full readback; deploy does not start the application. A private SFTP v3 metadata channel inventories all files, empty folders and stale transfer stages before reserving quota. The 96 MiB content budget remains below the 256 MiB FAT capacity; an additional largest-file stage, receipt overhead and registered output allowance are reserved. Transfer reads have OS file-size limits. Capacity/ownership/type conflicts preserve everything. A running VM pinned to an older exporter needs an ordinary explicit Stop/Start, never a worker-pin rewrite. Deploy requires an already started VM and cannot bypass the separate VM-start permission. Old C: records remain historical and are never moved or deleted.

Exchange runs use a fresh execution view after SSH authentication and complete owner/package byte checks. The deployment receipt remains historical; a normal boot/drive-letter change can rebind the same Exchange generation, whereas reset, component identity changes, missing files or modified bytes require a new deployment. Only terminal and service have launch adapters. Terminal starts yield a generation-owned handle; services receive a unique manual SCM name and report endpoint readiness separately from process start. The independent watchdog, bounded output, explicit stop and confirmed cleanup remain in charge after the agent turn ends. Working directory is the package; registered output filenames cannot replace package/control receipts. The inspected kernel's null-terminated argument buffer allows 127 UTF-8 bytes; SCM allows 95. Guest code is never silently truncated. The controller advertises `exchangeRunVersion: 1`; redeploy once to obtain this controller. Desktop launch is refused before guest effects and the old fake window-ID assignment has been removed. No app sources or SDK files are rewritten.

Agent `deploy_project` and `run_project` retain their original names, arguments and permissions. The harness attaches a durable job link before holding the native response open. Permission-scoped read-only long polls wait for the same job: deploy until confirmed publication, terminal until real completion and service until its owned endpoint is ready. Waiting does not require `read_development_job` and reconnects never resubmit a guest effect. Separate VM-start permission is still required; an older session can use a VM explicitly started in Virtual Machines or a new v3 session. Native declarations already persisted in old conversations are preserved; their earlier polling/autostart wording does not grant additional host rights. Current harness receipts and capability errors describe actual behavior. Browser status refreshes remain presentation only.

### SSH deployment operations (0.3.57–0.3.63)

The browser displays durable host receipts in existing expandable session tool/job cards: SSH readiness, upload/readback, relative Build package path, process/service state and available output/image evidence. It never runs SSH, edits a live disk image or decides guest readiness. The unprivileged coordinator and release-bound workers hold VM/project leases and authenticate the fixed `r4os`/`rosebud` account through private loopback SSH forwarding with pinned guest hostkeys. The guest controller owns its exact process/service generation and independent watchdog. SDK, application sources, project pins, base images and existing VM worker pins are unchanged by the rollout.

- A VM already running an older exporter must be stopped and started explicitly once. The next regular offline import publishes the identity marker and schema 2; the next boot pins the current exporter. Restart/reset of the guest alone does not replace its pinned host worker.
- Exchange shows the last offline host copy. Guest uploads appear there only after QEMU stops and export succeeds. Never edit `exchange.img` while QEMU runs. Root files and the bounded Build tree, including infrastructure, receipts, partial transfers and outputs, share the quota.
- A normal boot is reauthenticated and byte-verified before a new execution. Exchange reset renews the generation and requires deployment again. Image/system changes require new target/deployment admission. C: deployments remain readable history; no automatic move or deletion occurs.
- Interrupted transfer/control can remain `unknown`. Inspect the original job and preserved files; reconcile existing receipts without replaying a transfer/start. A missing receipt is not success. Explicitly stop the VM if its owned process cannot be confirmed ended; never clear quarantine by inventing an exit code.
- Offline export errors preserve the image. Resolve host/guest conflicts using the saved baseline or guest tree and use Retry exchange sync. Unknown newer sync schemas block safely; do not roll back to an exporter that cannot read schema 2. Image/system reset first recovers any committed merge journal; Exchange reset is the explicit destructive action.

Desktop integration remains open (0.3.61 tasks 1–3). `native_desktop_launch_contract_missing` is a capability error, not an image allowlist. It requires a public native headless launch receipt and window/client-size initialization barrier before application execution, plus correlated first-frame evidence. No studio_gui sources, fake window ID, artificial canvas or fixed-delay workaround is used. No SDK files were edited.

Validation for these changes is Python syntax, Studio build/TypeScript and lint plus ordinary release-install health. No tests, test projects/VMs, helper/app build probes, SSH guest probes, agent inference, application runs or runtime qualification were performed. The guest helper is rebuilt from its separately pinned source only when a user later requests a real deployment.


### Update Inbox transport (0.4.15)
Project package jobs can publish a confirmed immutable package using POST /api/projects/:id/update-packages/transfers. The accepted package/project/VM binding is frozen; full SYSUPD/installed-release/inventory preflight runs again under the same VM reservation. The scoped pinned OpenSSH client carries bounded SFTP v3 frames. Studio writes only an unused short Uxxxxxxx.TMP in C:\\R4OS\\UPDATE\\INBOX, requires CLOSE acknowledgement, reads every byte back and compares size/SHA-256, then uses native create-only RENAME to the paired .R4U and verifies it again. Existing names are preserved. This action does not invoke SYSUPD VERIFY/STAGE/APPLY/COMMIT or start/reboot a VM.

Durable intent/path/hash/target receipts precede writes and rename. A lost mutation acknowledgement or cancellation after write intent remains unknown; reconcile reads only the original two paths and can confirm an exact final file with absent TMP after a recorded rename intent. No write is retried. Native SSHD privately stages OPEN writes and publishes on CLOSE; interruption can remove its unpublished private staging file. A visible partial TMP is therefore not promised. Failed or ambiguous material stays available for later recovery. The client has 16 KiB chunks, bounded frames/diagnostics and a 420-second job deadline; no new dependency, generic remote-path endpoint or guest script is added. Local reservation and fresh STATUS do not lock out a separate native administrator; native checks remain authoritative. Host/data/worker protocol 1 and existing native agent tool profiles are unchanged.


### Native package installation (0.4.16)
POST update-packages/installs accepts 1–16 confirmed transfer job IDs from the assigned VM/system. It checks immutable packages, one target release, distinct native targets/package IDs and the aggregate 32 component/requirement limits. Under one VM reservation it repeats full preflight, hashes each published Inbox file, requires public SYSUPD VERIFY against the installed state for all packages before the first STAGE, then verifies again immediately before each STAGE. Cross-package missing dependencies are not silently deferred.

Actual STAGE replies select the result: effective APPLY needs a matching cleanup transaction and exact installed inventory components; true staging retains the native batch ID, package mapping and awaiting_commit state. Separate POST update-packages/commits requires the exact update revision, VM revision, batch, target release and confirmReboot=true. COMMIT is issued once with a durable intent and may reboot; its response alone remains unconfirmed pending post-boot proof (0.4.17). No QMP reset substitutes for native installation. GET update-packages/installations and installations/:id expose durable records. Existing agent profiles have no new update permissions; dedicated declarations/rights follow in 0.4.19 and browser workflow in 0.4.20.

A central VM owner plus project history retains all intents/actual captures and blocks competing Studio development mutations while commit/recovery is pending. Original request replay returns its original job. Native global commands lack an expected-batch parameter: a fresh exact STATUS comparison and Studio leases cannot atomically exclude an independent guest administrator. Such concurrent native writers remain unsupported; stronger serialization requires a native API extension. Inventories/version files and native private journals are never written by Studio.


### Post-install and post-boot proof (0.4.17)
COMMIT now enters bounded reconnecting/reconciling observation after its one original intent, including a lost SSH acknowledgement. It never resends COMMIT, resets QEMU or treats RESUME-BATCH as a probe. An independent POST update-packages/verifications action accepts the current update revision, a 30–300 second total observation deadline (default workflow 120) and an explicit fullArtifactHashes choice. Reads use bounded backoff and the original VM/system/host-key identity; changed keys require explicit identity review. Native UpdateService may already have finished the batch before the first reconnect.

Installation proof requires the own terminal batch or last live transaction and every exact component kind/name/target/version in two matching full MODULES.JSON reads. Requested full byte proof reads only exact immutable manifest targets over a dedicated read-only SFTP client and compares every byte count/SHA-256 to its source artifact. A final STATUS must still match. VERSION.R4S and VER record the visible installed release and active kernel independently of base-image ID/hash; a live update may leave the visible release unchanged. Deadline, missing correlation, rollback/foreign state or wrong hashes stay unconfirmed. No inventory/version/native journal is edited.

Native mutation intents invalidate guest readiness and assign a new update epoch. New deployments bind that epoch; execution rejects deployments from before the system change. Project pins and base-image identity stay fixed, while a successful fresh proof restores readiness for the current observed boot. Historical results remain historical evidence.

Observed Full0.87.14 limitations: the selected SDK default /SOFTWARE target is not classified by this guest and native VERIFY rejects it. Existing long target filenames can be updated, while creating a missing long filename is not an atomic native update operation. Studio preserves the actual SDK catalogue/manifest target; it never silently inserts a prefix or bootstraps a missing application. Qualification uses a separate own VM with an explicitly preinstalled own application and an explicit guest-supported source-manifest target.


### Owned native recovery and transport cleanup (0.4.18)
POST update-packages/recovery accepts only an existing own update ID/revision, current VM revision, target release and one fixed action: resume, resume-batch, abort-batch, rollback-last or cleanup. RESUME changes a known own live transaction. RESUME-BATCH can enter COMMIT for a prepared batch and reboot; its actual COMMIT reply is supported. ROLLBACK-LAST also requires explicit reboot confirmation and the exact latest proven native update. Fresh native state is checked immediately before each command. An unexpected preparatory state change without an own transition intent or a newer foreign transaction/batch blocks the action. No caller-selected shell command/path/VM or direct journal/stage/lock/backup manipulation exists.

Rollback is a separate outcome, never installation success. Original pre-install inventory and, for new installations, bounded full previous-file hashes prove restoration. Older update records without byte snapshots report that limitation. A live recovery identity can be reconstructed only from its original STAGE intent, exact unique source path, matching native package version/release/component count and a full immutable package readback. source=- alone and a bare batch ID cannot establish ownership. If a lost STAGE response contains no correlatable identity, preserve its native state for explicit diagnosis; the current native API cannot safely bind an unowned batch. Global commands still lack an atomic expected-batch argument, so another native administrator must remain inactive during Studio orchestration; stronger guarantees need a native API extension.

Pending/unknown updates keep their owner through session stop, worker/host/web restart and VM stop. They block competing development/VM mutations, project settings, editor maintenance and project deletion that would discard recovery evidence. Explicit VM stop/start remain possible under the existing reservation; they do not clear an update owner or imply rollback. New and already queued release-bound VM workers are checked at admission. Historical terminal records from an explicitly replaced VM system remain history rather than ownership of the new system. Base images, productive VM processes and project pins are preserved.

Cleanup is a separate, revision-checked action after correlated terminal installation/rollback or confirmed prepared-batch abort. It reads only the original TMP/R4U pair, removes only complete matching package bytes, preserves partial/different files and rechecks native status before removal. Lost REMOVE/close acknowledgement remains unknown; original-path reconciliation only reads and never repeats a removal. A clearly new explicit cleanup action can reauthorize remaining exact bytes. Transport diagnostics, package hashes, original native responses and private update history remain durable. Listing returns bounded summaries; each full record has a 2 MiB quota. English browser workflow and dedicated frozen agent permissions follow in 0.4.19/0.4.20.
