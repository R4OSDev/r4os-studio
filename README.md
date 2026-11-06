## 0.11.34

0.11.35 corrects Vision fallback eligibility for models with confirmed image input but omitted output maxima or optional reasoning detail. Local helper bounds remain separate from provider metadata; the native OpenAI account transport retains its own request contract. Main model, image originals and original operation receipts remain unchanged.

Project and skill sessions show “Waiting for limit reset” and “Stop waiting” only for a confirmed active reset wait. Cancellation has an owner/session/wait/revision-bound original receipt, persists across reply loss/reload, and ends only future automatic continuation and its monitoring demand. Shared checks and an already admitted run continue. Session events and existing recovery reads share monotonic wait revisions; no new session poller or confirmation dialog.

## 0.11.33

Registered primary quota waits admit one continuation of the existing conversation only after a fresh matching positive account observation and the full original process/tool/context barrier. Accepted model/provider changes cancel the intent immediately, including next-run choices; switching back never restores it. Human queue input has priority, Goal controls/budgets remain authoritative, and a repeated quota rejection never creates an inference loop. Original requests and uncertain launch outcomes are read, never replayed.

## 0.11.32

Only newly accepted, proven primary quota stops register durable reset waits in the existing session journal. Complete negative model responses and concrete fresh account observations remain distinct from unknown transport outcomes, generic 429s, Vision errors and local Goal budgets. Registered waits share existing bounded account readers without holding model workers or inference leases. No historical session is activated; automatic continuation follows in 0.11.33.

## 0.11.31

Visible AI Limits and AI Provider views request fresh Z.AI monitoring on opening/return and roughly every minute. The existing bounded helper and original receipts merge concurrent automatic/manual demand. Durable attempt times, 60–900 second error backoff and provider Retry-After are independent of the last successful observation. Hidden views add no demand; no model request or session continuation is started.

## 0.11.30

Z.AI subscription monitoring accepts the canonical Chat Completions and Messages endpoint pairs from one shared endpoint contract. Both retain the fixed quota GET, original credential revision and raw monitor authorization. Crossed endpoints, other products and hosts remain rejected; the model connection is never rewritten.

## 0.11.29

Assigned VM screenshots support capture-only and explicit external Vision analysis without changing the main model. `studio_capture_vm` accepts `analysisQuestion` or `action=inspect` for an existing image. A usable configured fallback is required for non-Vision capture. Failed analysis retains the image; capture, gesture and inference are never automatically repeated. Native Vision and explicit GUI assessment remain separate.

## Bounded external Vision operations (0.11.28)

A private image-to-text helper uses the existing Responses, Chat Completions or
Messages transport once, without tools or an agent loop. Its original operation
binds parent run/tool, authorized screenshot/hash/question, settings revision and
actual connection/model facts. It holds a separate purpose-bound credential
lease, retaining the main lease and selection. Raw responses, reported usage,
request hash and actual child process end use the existing model journal and
statistics, attributed to the Vision selection. Duplicate delivery reads its
original result, including unknown outcomes, without another request.

PNG integrity/pixel/byte limits, a conservative complete-input byte ceiling
within the documented context, explicit output-token limit, 16 KiB result bound
and 90-second deadline bound each request. Byte admission is not a reported token
measurement. Only actual provider usage is counted. Stop closes the child;
settings changes keep admitted selections frozen. Disconnect blocks/cancels that
connection, preserves its credential until confirmed end, and does not create a
hold for a different main provider. Original unit/process recovery can release
child leases without repeating an inference. Screenshot integration follows in29.

## Vision fallback settings (0.11.27)

System → Settings → Fallback optionally saves one existing connection/model for
requested image analysis. Its independent revision and original Save/Clear
receipts share the existing global Settings.sqlite; prompts, backups and restored
settings keep their own values. Only confirmed image/text/transport/default facts
qualify a target; function tools are not required. Unavailable saved identities
stay visible. Reading or saving never probes, signs in or calls a model. Drafts,
receipt recovery and explicit original-request retry survive navigation/reload.
The actual bounded image helper and screenshot integration follow in 28–29.

## Read-only system tool metadata (0.11.25)

The protected Settings tools API reads the installed original Studio contracts,
preserves scope variants, and pages prepared MCP metadata bound to the current
published skill/source/runtime/catalog identity. Details retain the original JSON
Schema, including operations, references and required fields. Native coverage is
explicitly partial when installed metadata does not declare built-in schemas;
permission capabilities are identified separately and never counted as tools.
No runtime, discovery, provider probe, login or inference is started. A narrow
bounded metadata reader avoids hashing executable programs, while execution
validation remains unchanged. Missing/changed sources cannot reuse older cached
metadata. System → Tools (#system/tools) now uses column 1 and the full remaining width.
Closed accordion rows load no details; pages contain at most 60 tools per source,
with explicit continuation and a shared three-read limit. Source changes and
expired access discard old responses. The top Tools tab stays the Skill workspace.

## Assigned project VM lifecycle tools (0.11.20)

The GOAL timer now follows a durable monotone session cycle through normal run
changes and reload. Pause freezes the measured prefix; Start resumes it; Stop
creates a new zero display cycle while the current run continues. Saving controls
show an explicit pending timer until their original receipt confirms them. Clock
responses carry owner/session, control revision and cycle ID so older ticks cannot
restore a reset. Historical goal_clocks, numeric outbox receipts, total runtime,
usage/costs and consumed budgets remain intact; the resettable display is separate.
Known legacy display prefixes and overlapping older executions are retained with
honest coverage and are never re-counted as new time. Existing bounded statistics
reconciliation transports the original new cycle receipts; no second clock poller
or database was added.


GOAL **Start / Pause / Stop** now control session keepalive. Start during a run
changes only the next boundary; an idle session starts one ordinary run with the
saved objective. Pause preserves the clock; Stop immediately resets it. Both
leave the current prompt, permissions, model/tool rounds and processes running
normally. **Stop current run** remains a separate action. Automatic Goal runs
use the normal coordinator admission/launch path after confirmed whole-process,
tool and history end. Human queued input keeps priority and its frozen selection;
next-run model choices apply at their existing full boundary. Original commands
and control generations prevent duplicate/late continuations. Current Goal runs
retain their original context when later controls change, and complete/blocked
reports cannot overwrite a newer Goal generation. Native histories and active
older workers are preserved.


System → Updates → R4OS Releases offers **Update VMs** immediately after
**Use as default**, independently of the selected default. Its Cancel-first
preview lists all source/target releases and statuses and explicitly confirms
graceful shutdown, C:/D: and program deletion, preserved Exchange/settings/
assignments/access, and stopped final VMs. Changed VM snapshots require a new
preview. One browser ticket follows the original batch through reload/navigation;
response loss reads its original receipt, with explicit same-request retry only.
The batch target stays fixed when the dropdown changes. Progress distinguishes
updated/current/pending/blocked/failed/unknown, and confirmed changes invalidate
the existing VM overview.


Manual R4OS release batches use a saved preview of all current VM identities,
source revisions and the selected local Full-image checksum. Confirmation
explicitly allows graceful shutdown and replacement of C:/D:. A single serial
background operation holds each VM maintenance lease through shutdown/export and
the existing atomic release swap. Exchange, VM identity and assignments remain;
VMs stay off. Already-current disks/revisions and the global default are retained.
One verified image is shared by exact inode/size/nanosecond modification facts;
changed images hold remaining targets. Private original child receipts recover
committed swaps without replay; unknown steps remain visible. After a host restart,
only explicit continuation processes the original untouched pending targets.


Project agents now have separate **Start project VM**, **Stop project VM** and
**Restart project VM** switches under Session settings → Tools → VM. Restart
also requires the run's Start and Stop permissions. Existing sessions receive the
current catalog for later work; active runs, accepted queues and Goal Play
commands retain their captured tools and permissions. Skill sessions cannot use
these project tools, and agents cannot supply another VM ID or a host command.

Stop requests graceful shutdown and waits for the original process group,
service/export workers and Exchange synchronization to finish. Already fully
stopped is a confirmed no-op; Stop requires no SSH login. Restart holds the same
reservation across stop/export and one subsequent start, then requires a new
boot and fresh authenticated SSH/VER readiness. Use Start for a stopped VM.
No lifecycle tool forces a shutdown or changes VM settings, images or pins.

The tool waits in Studio's harness and retains its original job link. A lost
reply, timeout or cancellation never automatically repeats a power action.
Unconfirmed power phases preserve their receipts and block further lifecycle
work through the existing quarantine. Recovery reads committed original stop or
readiness receipts; it cannot infer success from the VM's present state or
replay shutdown/start. **Stop job** continues to cancel only its own job.

## Exchange file manager (0.11.19)

System → Virtual Machines → a VM → **Exchange** now has a folder tree,
clickable path, Up/Refresh, selectable Name/Type/Size table and compact status.
Use the arrow keys to select rows, Enter to open a folder, **Upload file** for
files up to 8 MiB, and **Remove** for the selected file or empty folder. Narrow
views keep path navigation and essential actions available.

**Empty Exchange** clears the whole selected VM's exchange drive, including
root/subfolder files, guest exchange files, conflicts and pending synchronization.
Its confirmation names the VM and starts with Cancel focused. System disks,
base image, VM settings, project assignments and saved access are retained.
The existing reset requires the VM and export workers to have fully stopped,
an exclusive development lease and its original revision. It never starts or
stops the VM. Settings → **Reset Exchange Partition** shares the same controls.

After a lost response, Studio preserves the original request across reload.
**Check original reset** reads its receipt; **Retry same reset** explicitly
reuses its exact ID and confirmation. An uncertain reset keeps mutations guarded.
A confirmed failed preparation can be closed before reviewing a new request.
Only confirmed completion refreshes the inventory and returns to the root.
Last host copy, actual last synchronization, pending errors and sync retry remain
visible; host edits apply at the next start.

## Change the next model during a run (0.11.18)

In project and skill sessions, **Model** remains available while a run is active.
Choose a compatible model on the same connection, then save. Studio shows the
current run model and the pending choice separately. Cancel the choice to keep
the saved model for future inputs; already accepted queued inputs retain their
original model and credentials.

A choice never starts or interrupts a run. The complete current run, including
tools, retries, steering and Goal rounds, keeps its frozen configuration. Before
admitting subsequent work, the host verifies the original process and tool
receipts, current model/credential facts and the complete conversation context.
An unresolved outcome or incompatible context leaves a visible blocked choice.
After a lost save response, check its original receipt or explicitly retry that
same request. Reload preserves the request, draft and attachments.

## Native OpenAI browser sign-in (0.10.21)

Choose **OpenAI · ChatGPT subscription** when connecting a new account.
Continue with ChatGPT, complete OpenAI sign-in in the other browser tab, then
paste its complete final redirect address into the original Studio form.
The localhost page may report that it cannot connect on another computer;
its address still contains the one-time sign-in result. No helper, terminal
or desktop installation is needed on the browser computer.

Studio keeps native account access privately on its host. A confirmed sign-in
updates immediately and shows the selected workspace and its account limits.
Each account has one token-renewal owner. Model transport is prepared separately;
an account selected for Studio never falls back to running a native agent when
that preparation is missing. Existing direct ChatGPT plan connections and old
native conversations are preserved until deliberately changed.

## Common Studio conversations (0.10.19)

Connect a **ChatGPT plan**, **Z.AI Coding Plan** or an explicit API endpoint in
System settings. Direct connections share Studio's conversation, tool, context,
Goal, queue and Stop code over Responses, Chat Completions or Messages. They
need no Codex/Claude/OpenCode agent process. ChatGPT plan sign-in runs in the
browser: complete OpenAI sign-in and paste the full final redirect address into
the original Studio tab. No helper download, CLI or API-key conversion is needed.

Refresh model metadata explicitly, then select an available model. Creating a
session or saving a connection sends no message. Account/model choices apply to
future inputs and preserve the draft and original results. Finish or resolve
already accepted work before changing its connection. Session settings →
Conversation offers a deliberate conversion for compatible idle old sessions;
opening a session or upgrading never converts it automatically.

Existing native accounts/history and frozen workers remain supported. Claude
subscription access and native hosted image generation still require their
specific native connection. The standalone patch utility is needed only by the
existing Apply patch tool; ordinary direct model/file operations do not require
a native model runtime. No hidden account, model or paid API fallback is used.
See [Agent runtime](Agent-Runtime.md) for protocols, original receipts, media,
limits, conversion and the exact remaining native boundaries.

## Status and provider settings (0.10.46–0.10.47)

The workspace tabs are Status, System, Projects and Tools. Status → AI Limits
is directly accessible at `#status/ai-limits` and uses one navigation column;
its content occupies the remaining width. Provider connections are managed
under System → Settings → AI Provider. Existing connection identities and
project/skill routes are preserved.

AI Limits shows one card per configured account or connection. Each reported
allowance has its own remaining-percentage ring, with the official reset below
it. Green means remaining; red means used. Missing resets stay unknown, and
stale or unlimited observations remain distinct from zero allowance. Repeated
representations of the same account or budget do not create extra rings.
The dashboard and provider details share their observations and original refresh
requests. Viewing limits never starts a model run or consumes an earned reset.

## Local project files

Every project workspace has an initially empty `ExFiles/` directory for local
archives and other external data. Its entire contents, including subdirectories,
are excluded by `/ExFiles/` in the project `.gitignore`. New projects and GitHub
imports create the directory automatically. The private Git repository also
keeps this local exclusion if a later pull changes `.gitignore`.

Project sessions can access these files as `ExFiles/...` through their existing
file tools, or `/workspace/ExFiles/...` through **Run command**. Git exclusion
does not make the directory read-only or include its files in a built app.
Builds exclude the project-root `ExFiles/` directory and its entire contents
from the source snapshot, input limits and build identity. This applies to both
manual and agent builds. Keep required app resources in ordinary build paths;
other `.gitignore` entries do not exclude files from build inputs.

## Z.AI GLM Coding Plan (0.9.39–0.9.45)

Connect **Z.AI · GLM Coding Plan** in LLM Provider settings with your plan API
key, then select its model in a normal project or skill session. Studio uses
your Coding Plan endpoint and the common Studio worker, with the authorized
OpenCode client identity. Existing native conversations retain their original
worker until explicitly converted. There is no paid standard-API or model fallback.

Provider settings and sessions show original account-wide credit windows,
remaining allowance, reported resets and confirmed limit reasons. Refresh
updates those observations without starting or resuming work. Session token
statistics stay separate. Keys remain private and write-only. See
[ZAI-Coding-Plan.md](ZAI-Coding-Plan.md) for behavior and qualification boundaries.

## SDK-owned profiles and complete migration (0.9.28–0.9.35)

Select one complete official SDK package in **System → Updates** or the project's
**Settings → Pins**. Its original Build, Tools and Components profiles determine
compiler and system libraries. New/imported projects and isolated offline builds
use that SDK's native catalog and drivers. Missing, changed or legacy pins produce
an explicit error. Own libraries need real dependency edges; Development builds
require an explicit technical receipt.

The installed projects and internal helpers were migrated together to SDK
0.64.145. Old installed SDKs, operational source/tool caches and SDK archives were
then deleted. The updater prevents reactivation of the retired system. Existing
user source, session histories, original jobs, confirmed artifacts and VMs retain
their identities. Read [SDK-Profiles.md](SDK-Profiles.md) for operation and
[SDK-Qualification.md](SDK-Qualification.md) for exact native evidence and limits.
Older version entries below record historical behavior.

## Short native SSH shortcut guide (0.9.27)

The default system prompt and effective project instructions now carry one short
SSH guide for a user-requested desktop link. It gives the six R4LNK fields,
actual target-path substitution, separate ECHO/TYPE commands, native byte/right
limits and the embedded-icon meaning. The guide is conditional on the declared,
enabled VM SSH tool; unavailable tools receive a short retirement notice instead.
Custom saved text and accepted prompt snapshots keep their original hashes and
revisions. The next normal run in the same session receives the current guide,
without a new thread. Skill Manager instructions receive no guest guidance.
See [Project-VM-SSH.md](Project-VM-SSH.md) and
[shared/project-vm-shortcuts.txt](shared/project-vm-shortcuts.txt).

## Project VM SSH and retirement of desktop automation (0.9.25–0.9.26)

Project agents can run free native guest commands using **Run VM SSH command**.
Studio derives the assigned VM and keeps SSH credentials/host trust private.
Commands return durable original jobs, with output, actual shell exit receipts
and client-only Stop semantics. See [Project-VM-SSH.md](Project-VM-SSH.md).

Studio no longer publishes desktop shortcuts or activates managed links. The
old buttons, request options, publication/ownership code and specialized guest
helper commands are removed. Obsolete requests receive a specific removed
feature error before guest effects. Ordinary build/deploy/run, capture, input,
window controls and R4X icon embedding remain available. Existing guest links,
original jobs and immutable releases are preserved. Historical desktop records
are read-only; no automatic recovery publication or replacement launch occurs.
A shortcut may be created by an agent over project VM SSH only when requested;
the short native guide is supplied with the next regular project run.

## Roadmap and remaining sidecar profile checks (0.9.24)

The Roadmap sidecar now uses the actual project owner, enabled Roadmap setting,
original tool intent, inherited workspace lease and exact worker identity.
A leftover list of former profile names had denied Roadmap reads in every new
conversation even though its current tool catalog allowed them. Skill authoring
and GUI window, gesture, drag interrupt, key-plan and editor-shortcut paths also
use their explicit frozen owner/permissions instead of obsolete profile names.
Native helper capabilities, own-process/window grants and fresh frame checks
remain required. Historical receipts and active workers keep their original
bindings. The fix applies on the next normal run in the same session; it does
not require another conversation or replay a failed call. No tests or guest
runs were executed. See [Active-Tools.md](Active-Tools.md).

## Bounded execution mailbox cleanup (0.9.23)

Closing an execution now resolves queued and already dequeued action responses,
allows a short error-delivery interval and closes its own connections before
waiting for the server to finish. All connection cleanup waits are bounded.
Requests not admitted to execution are distinguished from unconfirmed original
guest effects. Unexpected action failures settle their original response
immediately and preserve a bounded first-cause diagnostic before cleanup, with
the exception type, optional missing metadata field and original action binding.
Tool arguments and credentials are excluded. A socket closing is never proof
of application completion or guest cleanup. Existing unknown jobs remain
protected; no launch, input, screenshot or close request is replayed.

## Historical: Screenshot binding after native link activation (0.9.22)

Removed in 0.9.26. The following records the earlier implementation only.

Screenshots of apps started through their published link retain the original
`desktopLinkActivation` receipt, separately from ordinary DESKRUN metadata.
Before capture, Studio verifies the saved canonical Prepare request, request
SHA-256, original publication/link and native process generation. Image input
and completion retain this launch binding alongside the existing boot, process,
window, geometry/focus and observed-interval checks. Missing proof returns a
specific capture error. Historical images and launch receipts are preserved.
This host-side fix needs a new execution worker; it does not alter guest helpers
or replay any previous launch, input, capture or close request.

## Original deployment path recovery (0.9.21)

Deployment reconciliation now normalizes both the stored native directory and
the directory derived from its original target. A verified Exchange directory
such as `F:\Build\...` no longer fails because only one side was uppercased.
Original VM, artifact, pins, full file hashes and publication evidence remain
required. An already durable publication observation can finish the original
recovery without another guest operation or publication.

## Historical: Replacing desktop links and reconciling legacy publications (0.9.20)

Removed in 0.9.26. The following records the earlier implementation only.

The private guest helper now accepts the SDK's named checked-delete results:
`deleted=1` and `not_found=0`. Negative results remain failures. Replacement
still requires the original backup bytes, exact final link readback and absent
stage/backup files. Bound failures retain their phase and native return value in
create-only `DSKERR.JSN` and stdout. New deployments obtain the corrected helper;
existing deployed binaries and project component pins remain unchanged.

For the identified older helper's recorded exit113, **Reconcile receipts** can
confirm the current publication from the original intent marker, every original
deployment file's full SHA-256, exact new link bytes and absent TMP/BAK, under the
same VM service identity and a current reset observer. The separate host file
observation records `nativeCompletionReceiptAvailable=false` and preserves the
original exit113; the reconciled job has no invented exit0. It never republishes
the link or starts the application. Missing or differing evidence stays unknown.
See [Desktop-Shortcuts.md](Desktop-Shortcuts.md).

## Historical: Desktop publication and activation without profile gates (0.9.19)

Removed in 0.9.26. The following records the earlier implementation only.

Desktop publication and native link activation now use the existing actual
project/session/worker authorization without reading a former engine profile.
Two leftover generation checks could otherwise fail current runs with the
misleading coordinator-unavailable message before admitting a job. Deploy/Run
permissions, original artifact/publication bindings and real guest capabilities
remain required. No old request is automatically resubmitted. Static checks only;
see [Desktop-Link-Activation.md](Desktop-Link-Activation.md).

## Historical: Native link request transfer (0.9.18)

Removed in 0.9.26. The following records the earlier implementation only.

The verified Exchange path guard now accepts the native link helper's exact
short request filename derived from its original lowercase execution UUID.
Previously a valid native Prepare could be followed by a local path rejection
before Activate. The request name, guest recovery contract, package-root binding
and full byte/hash readback remain unchanged. No guest-helper rebuild or project
pin update is needed. Static checks only; no test or guest activation was run.
See [Desktop-Link-Activation.md](Desktop-Link-Activation.md).

## Runtime metadata in the hardened web service (0.9.17)

The final installed HTTP check found that 0.9.16 attempted native feature
discovery during session storage reads. The web service deliberately cannot
mount the private `/proc` required by Codex; this incorrectly hid a valid
default as unavailable. Session options and reads now inspect only installed
metadata and integrity. The separate coordinator and workers discover native
features when accepting or executing new work. Service restrictions are kept.
Image capability receipts match the original runtime identity rather than the
presence of derived feature fields in a public metadata view. Existing accepted
receipts remain unchanged. This completes the 0.9.16 roadmap integration;
published 0.9.15/0.9.16 tags are retained.

32 focused checks, Python AST, product build/TypeScript and lint passed.
The corrected metadata read was also executed under the actual web service
mount namespace and unprivileged identity, with its restrictions unchanged.

## Codex features follow the selected runtime (0.9.16)

Codex sessions no longer depend on a fixed Studio version or binary allowlist
for tools, Goals, messages, image input/generation, context or usage capture.
Studio reads active boolean features from the selected binary in an isolated
namespace without credentials, network access or model calls. Removed aliases
are excluded; native features start disabled and only the requested Studio
features are enabled. Real missing capabilities remain specific function errors.

Provider version headers use the actual runtime. Context and usage identify
the original execution; old totals are neither relabeled nor counted twice.
Image recovery verifies the original installed pin without starting Codex.
Retry evidence distinguishes thread creation from the original run version
and retains strict record coverage, original effects and control checks.
Accepted queues keep their original runtime and capability snapshots.
The independent private Claude patch helper keeps its own existing pin.

31 focused checks passed, including changed binary bytes, default changes,
unchanged queue captures, original-runtime usage, context, image policy/recovery
and bounded retry evidence. Actual unprivileged checks of 0.163.0 and 0.166.0
confirm feature discovery, provider capability reads, patch execution and the
same native thread with its paused Goal across a version change. These checks
did not start model turns or new provider-side image generations.

## Codex follows the Studio default (0.9.15)

New Codex sessions and newly accepted requests in existing conversations use
the complete local Codex installation selected in Studio Updates. Its version,
binary path and SHA-256 are frozen with that request. There is no separate
Studio version approval or requirement to return to Codex 0.163.0. Native
threads and histories are retained when the default changes.

Already accepted queues and running workers keep their original runtime.
Binary integrity is checked against the selected installation and the accepted
request; a missing or changed installation produces a concrete error without
a silent fallback or replacement conversation. Session settings show the
runtime selection, and original runs retain their own version and hash.
Feature-specific version conditions are addressed separately in 0.9.16.

Eight focused runtime-selection checks and an unprivileged native metadata
check passed: the same isolated thread resumed through 0.163.0 → 0.166.0 →
0.163.0 with its paused Goal intact and no model turn. Product build,
TypeScript and lint passed. User sessions, runtime defaults and VMs were not
changed for these checks.

## Catalog receipt before conversation resume (0.9.14)

The Codex worker now imports the atomic JSON writer used to save its current
tool-catalog receipt. A missing import in 0.9.13 aborted runs after the catalog
comparison, before starting a model turn, even when the saved tools already
matched. Receipt-write errors now have their own message, distinct from catalog
refresh errors. Existing conversations continue in the same thread. No tests or
model turns were used for validation; see [Active-Tools.md](Active-Tools.md).

## Current tools in every existing conversation (0.9.13)

Sessions now use the installed tool catalog on their next run or continuation.
Session creation dates and former v1–v23 profiles no longer restrict tools,
arguments or settings. Explicit saved switches remain; newly available tools
receive their normal defaults. Codex resumes the same thread with current tool
metadata; Claude receives the current MCP catalog. Active calls and original
receipts retain their immutable bindings. This also corrects the v23 Git denial
and missing Environment Notes availability. Static checks only; no tests,
inference or application-repository push for validation. See
[Active-Tools.md](Active-Tools.md) and [Bound-Git-Selections.md](Bound-Git-Selections.md).

## Guest controller without an SCM slot (0.9.12)

The independent watchdog now starts through the public generation-bound console
host API, with its own console instead of the SSH console. It no longer registers
a temporary SCM service: a guest whose sixteen service entries are occupied can
still run desktop and console apps. Native service apps retain the guest's actual
service capacity limit. Deploy an existing artifact again to obtain the new
controller; old deployments, sessions, project pins and helper binaries remain
preserved. Current workers reject the old bootstrap contract before starting it.

Startup saves the original relay/watchdog identities and verifies the returned
watchdog generation before admitting an application start. Native startup errors,
bounded first response/stderr and final SSH client status are retained. Only an
explicit matching no-start/no-child failure releases the execution reservation;
missing replies and uncertain cleanup remain protected. No tests were run.

## Historical: Activate the original published desktop shortcut (0.9.11)

Removed in 0.9.26. The following records the earlier implementation only.

A verified GUI publication now offers **Run desktop link**. New v23 project
conversations can use `studio_run_project` with `desktopLink=true`. The coordinator
and worker recheck exact own-link and target bytes; the original watchdog saves
the canonical native Prepare request before one Activate. Recovery reads that
original request without another start. Start, frame readiness, end, output and
cleanup remain separate. Requires a new deployment and compatible R4OS0.89.18
runtime; original sessions, pins and deployments are preserved. No tests or guest
runs. See [Desktop-Link-Activation.md](Desktop-Link-Activation.md).

## Message admission in existing and new sessions (0.9.10)

The agent coordinator now loads optional original-job references independently
of the worker's module search path. Missing reference adapters or storage produce
an explicit unavailable marker instead of preventing run admission with a generic
coordinator error. Existing and new sessions keep their profiles and permissions;
no session recreation is needed. Static checks only; no tests or inference. See
[Original-Development-Jobs.md](Original-Development-Jobs.md).

## Original terminal lifetime and deadline (0.9.9)

Terminal replies/items now expose the original start, observed monotonic elapsed
time, immutable deadline and remaining lifetime for pipes and PTYs. Polling never
extends the budget; final observed duration is frozen and retained. Missing old
measurements remain explicitly unknown. Existing limits and declarations remain
unchanged. No tests or inference. See [Terminal-Lifetime.md](Terminal-Lifetime.md).

## Bound Git inspection and large explicit selections (0.9.8)

New v22 conversations can read paginated own Git status/diffs and original jobs
under a separate read permission. Push requires a reviewed immutable selection
and commit description, with up to512 files /65536 path bytes. Original branch,
base, statuses and hashes are rechecked before admission and staging; existing
source quotas and independent Push permission remain. No add-all default or
replay on a lost response. No tests or application-repository writes for validation. See
[Bound-Git-Selections.md](Bound-Git-Selections.md).

## Short own-client key plans (0.9.7)

New v21 conversations can schedule at most32 normal key/codepoint events over
2000ms in the original guest helper. Current own-frame/process/focus/geometry
bindings and input permission remain required. Original receipts retain accepted
prefix, actual dispatch-call times, lateness and abort reason; no held keys,
modifiers, global input or automatic replay. Existing profiles remain unchanged.
No tests, inference or app/VM runs. See [Own-Key-Plans.md](Own-Key-Plans.md).

## Own-client Select All (0.9.6)

New v20 conversations can send Ctrl+A as one native semantic GUI event with a
fresh focused own frame and a newly deployed editor-shortcut-v1 helper. No
physical modifier is held; existing key repeats and older declarations remain
unchanged. Ctrl+Home/End and clipboard operations are unavailable. Enqueue does
not prove application consumption. No tests, inference or app/VM runs. See
[Editor-Shortcuts.md](Editor-Shortcuts.md).

## Historical: Initial desktop link activation boundary (0.9.5)

Removed in 0.9.26. The following records the earlier implementation only.

The initial0.9.5 release reported native own-link activation as unavailable.
The then-qualified native contract had no recoverable link-activation receipt;
directly starting the resolved R4X cannot satisfy that acceptance. The new native
contract is integrated in0.9.11 above. UI and agent guidance distinguish these facts and preserve
original permissions and unknown effects. No tests or guest runs. See
[Desktop-Link-Activation.md](Desktop-Link-Activation.md).

## Recover original own job references (0.9.4)

New v19 conversations can page or locate their original session jobs by the
Studio request UUID or original run/toolcall. Existing conversations keep their
declarations and receive bounded recent references on the next authorized run.
A small durable request/job reference precedes detailed output; missing output
never implies rejection or authorizes replay. All lookup paths enforce own-session
read permission. No tests, inference or app/VM runs. See
[Original-Development-Jobs.md](Original-Development-Jobs.md).

## Continue own-client input after a rejected window action (0.9.3)

An immutable native rejection now settles only its matching original window
operation. It no longer leaves windowActionPending locked merely because no
applied frame exists. A fresh own view/frame is still required; actual pending,
unknown or mismatched operations remain protected and resize is never retried.
The original outcome survives scope reads. New deployments use the corrected
helper under unchanged private pins; old workers/helpers stay intact. No tests
or app/VM runs. See [Rejected-Window-Actions.md](Rejected-Window-Actions.md).

## Preserve original Desktop launch receipts (0.9.2)

A failed control-channel heartbeat no longer discards the already submitted
DESKRUN response. New launches persist an original host correlation receipt and
bounded transport diagnostics; valid original saved responses can be read back
without replay. Host UUIDs are never native request keys, and an empty lost ACK
remains unknown pending qualified native correlation. Source/receipt inspection,
AST and Studio static checks only; no tests or app/VM runs. See
[Desktop-Launch-Receipts.md](Desktop-Launch-Receipts.md).

## Natural Desktop completion observation (0.9.1)

When a naturally exiting Desktop app loses its window before its retained end
receipt arrives, the current worker reads only the original acknowledged lease
for up to five seconds. Exact original request/token/process matching is required;
no Q, Close, launch or Goal Play is repeated. Genuine end, actual exit code,
output completeness and helper cleanup remain separate evidence. Old workers
and historical unknown jobs are preserved. Source/receipt inspection, Python
AST, Studio build/TypeScript and lint were used; no tests or application/VM
runs. Native delayed-completion acceptance still needs original runtime proof.
See [Natural-Desktop-Completion.md](Natural-Desktop-Completion.md).

## Historical: Publish a project on the VM desktop (0.8.84)

Removed in 0.9.26. The following records the earlier implementation only.

Completed GUI R4X development cards offer **Deploy to desktop**. New profile18
agent sessions can set `desktopShortcut=true` on `studio_deploy_project` under
their existing Deploy project permission. Studio publishes one project/VM-owned
R4LNK with ICON=INTERNAL to the selected verified deployment. Normal test deploys
leave it unchanged. Existing or edited foreign links are preserved; original old
bytes/intent, atomic native publication, full readback and cleanup are retained.
Lost results are reconciled from original receipts only, without replay.

Current agent guidance explains Notepad's manifest/resource/link path and the
separate embedded-icon, link-byte and visible-guest findings. Earlier native tool
schemas stay unchanged; their browser action remains available. No app/VM start,
Goal/roadmap mutation, tests, fixtures or inference. Build/TypeScript/lint and the
pinned private helper builds are the checks; guest publication/visual proof is
still unqualified. See [Desktop-Shortcuts.md](Desktop-Shortcuts.md).

## Escape and own-window actions during a bounded drag (0.8.83)

New project sessions use profile17 and can interrupt a held gesture with Escape
or an actual delegated resize/minimize, followed by release in the same bounded
call. Window actions require their separate original run permission/grant. The
complete native request is persisted before input, submitted once and read only
by its original operation after uncertainty. Native apply while release is still
pending, composed frames and app consumption remain separate evidence. Existing
conversations retain their exact tool schemas; a new session and deployment are
needed for the new optional `interrupt` field. App artifacts/pins stay unchanged.

Outside-client drag routing remains unavailable to the helper: direct app queue
coordinates would bypass native capture, whose host owner is Desktop. The case
stays open pending a scoped native input delegation. No icon integration is
included. See [Drag-Interrupts.md](Drag-Interrupts.md) for the contract and limits.
Direct implementation without roadmap changes, tests, fixtures or inference;
Studio static checks and both pinned private helper builds are used instead.

## Retained completion after an owned check close (0.8.82)

An own Desktop process can detach before its retained native completion becomes
available. During an already-admitted `complete_development_job`, the worker now
allows up to five seconds of read-only polling on the same original controller
when that exact process generation temporarily reports unknown with an existing
retained-evidence lease. It sends no second close, input or launch. VM/job guards,
original completion request, process identity and user Stop remain binding.
Returned output is preserved while polling; a timeout, changed identity or missing
receipt retains the existing unknown protection. Successful completion still
requires the actual native end and original helper/service cleanup receipts.

Goal recovery can link the exact admitted check-completion intent to its original
job and any separately confirmed guest end. It does not certify that the unknown
completion call or cleanup succeeded, and never replays it. Minesweeper/Main's
actual late watchdog receipt confirms process83/generation83 and native exit0
after the original requested close; its historical incomplete completion remains
distinct from the successful visual assessment. Original records are preserved.

Direct hotfix without roadmap changes, tests, fixtures or model calls. Studio
build, TypeScript, lint and Python syntax are checked; no user app or VM is started.

## Read unknown jobs without stopping the Goal (0.8.81)

A successful `read_development_job` now confirms the read independently of the
original job state. Failed, interrupted, unknown and readiness-unconfirmed jobs
retain their actual status, evidence, checks and exit information in the result;
they no longer turn a status read into an unconfirmed new effect. Summary,
details, inventory and output views share this behavior. Missing permissions,
unavailable originals and invalid cursors still fail the read normally. Start,
input, window and completion outcomes keep their existing effect semantics.

Solitaire/Main's original window failure predates0.8.80; subsequent successful
reads of that old unknown execution repeatedly stopped its Goal. The original
guest closure is reconciled through the existing independent watchdog recovery,
with historical records preserved and app checks/output still inconclusive/
incomplete. Main remains paused for explicit Play. This direct hotfix changes no
roadmap and uses no tests, fixtures, model calls or user app/VM runs.

## Ordered own-window operations (0.8.80)

Resize, Minimize and Restore now reserve strictly increasing native operation
IDs within the original execution. WINSVC rejects numbers below its previous
operation; deriving them from random request UUIDs could make Restore fail after
a successful Minimize. The durable request UUID remains the idempotency key.
The counter is reserved before helper preparation, survives rejected preparation
and status reads, and fails before submission if missing, damaged or exhausted.
Existing deployed helpers support this host correction without redeployment.

An unknown native response with operation zero is reported as a missing original
receipt rather than a different operation. No uncertain command is retried.
Goal recovery links admitted own-window requests to their exact original
execution, including older error replies without a job link. It preserves the
unknown action and separately reports confirmed guest closure; it never claims
that Restore succeeded. Original watchdog completions may be read after a host
observer restart, with unchanged VM/image/package bindings and full original
helper verification. The old boot token is never used for a helper call.

This direct hotfix covers the actual R4Craft/Main and Minesweeper/Main Restore
failures, with no roadmap changes, tests, fixtures or model calls. Their original
watchdog frames confirm process closure after control loss; app checks/output
remain inconclusive/incomplete. Main stays paused for explicit user Play.

## Guest gestures and original watchdog recovery (0.8.79)

New helper deployments declare `gestureVersion:1` in qualification and in the
live controller, so a supported right-button gesture is no longer rejected by
missing deployment metadata. Existing deployments retain their original bytes;
deploy the artifact again to use the updated helper. The helper's saved-evidence
observer now advertises `desktopEvidenceRecoveryVersion:1` and uses matching
eight-character basenames on the Exchange drive.

For older observers, recovery can read the original independent watchdog's
final receipt after checking the unchanged VM/boot, original helper bytes,
controller/execution identity, process generation and native completion sequence.
This confirms only the original process end. Missed console output and app
criteria remain incomplete/inconclusive, and a control-loss exit remains a
failed execution even when the native exit code is zero. No helper, application
start or input is replayed. Prior unknown records and frozen configurations stay
intact; the new closure receipt is archived separately.

A committed image assessment now reports its own confirmed host effect instead
of inheriting an unrelated unknown execution state. Goal recovery can link that
exact original assessment receipt to the confirmed guest end. Malformed recovery
requests receive400 rather than an internal503. This is a direct hotfix with no
roadmap changes, tests, fixtures or model calls.

The actual original Minesweeper/Main process was reconciled from its final native
watchdog frame; its Goal remains paused in the same thread and ready for explicit
Play. Studio build/TypeScript/lint and both pinned guest-helper builds passed.
No VM was stopped/restarted and no user app was rebuilt, redeployed or launched.

## Project Settings → Pins (0.8.78)

Existing projects can now explicitly select an installed SDK under
**Projects → project → Settings → Pins**. The view compares current SDK, Contract,
Zig and applicable Rust versions, with expandable source revisions and checksums.
Contract and compiler bindings follow the selected SDK. Apply affects only this
project; active work and unsaved editor drafts block changes. Source files and
Cargo.lock stay intact, while portable project metadata and catalog pins change
together. A pin change validates components and the manifest; build afterwards
to check application source compatibility.

Lost responses and reloads retain the original request. Status checks only read
its receipt; explicit retries reconcile the same publication. Editor drafts are
kept and changed metadata is flagged for review. Actual pin switches and isolated
SDK127/Contract68 builds are qualified for Zig, C and Rust without migrating user
projects. Details and limits: `../Docs/Project-Pins.md`.

## Explicit pin changes for existing projects (0.8.77)

Project pin APIs select an installed SDK with its matching Contract and compiler,
validate the published component/tool identities and the existing app manifest
through the unprivileged development coordinator, and publish catalog and portable
`.r4os-studio/project.json` pins together. Project-wide idle admission, durable
request receipts and a recovery gate protect interrupted publication. Source
files, Cargo.lock, other projects and global defaults are preserved. No app build
or runtime success is implied. The Project Settings → Pins interface is available
since 0.8.78; architecture and limits: `../Docs/Project-Pins.md`.

## Environment notes for upstream faults and feature requests (0.8.76)

Reporting policy2 explicitly covers observed Studio/tool/workflow faults and
faults in dependencies outside the agent's accessible project: public APIs/ABI,
SDK/Contract, kernel, Desktop and libraries. An upstream component is a valid
reporting target even when it is a separate application or repository. Reports
identify the known component/version, operation, expected/observed behavior and
impact using available evidence, with suspected causes distinguished from facts.

Concrete API extensions, Desktop functions and library functions that simplify
the actual workflow can be reported without a preceding failure. The existing
separately filterable **Suggestion** type (`kind=suggestion`) identifies these
requests; category continues to describe the affected area. Record the missing
capability, use case and benefit. Ordinary bugs in the editable app project,
expected permissions/Stop and corrected misuse retain their existing treatment.

Both tool descriptions and the common runtime instruction block carry the scope.
The block replaces earlier note guidance on compatible new runs/resumes with
Environment notes enabled. Existing native threads keep their original dynamic
tool declarations; new threads receive the updated descriptions. Schemas, tools,
permissions, saved global/project prompts and original notes remain unchanged.
Read-before-write, deduplication, concise private content, no reporting quota or
extra investigation solely for reporting, and user-deleted-note protection remain.
Six existing targeted note tests, schema/source review, Build/TypeScript and lint
verify the update without model calls or production note creation.

## Session deletion after completed upload failures (0.8.75)

Session deletion now recognizes rejected uploads and confirmed purges as terminal
attachment receipts, alongside ready and removed attachments. Previously, an
unsupported file or an earlier validation failure permanently blocked deletion
with an active-or-unconfirmed attachment message. The same issue affected files
whose unused originals had already been fully purged.

Pending uploads, uncertain outcomes, incomplete removal and unfamiliar states
still block preview and confirmed admission. Original receipts and attachment
bytes remain intact until the user confirms the ordinary session deletion.
Project and skill sessions share the correction; the Yes/No dialog is unchanged.
Eight targeted deletion tests cover actual rejected uploads and completed purges,
both owner scopes, unchanged originals before confirmation, unrelated sessions,
active/unknown/cleanup states and existing deletion recovery. Build, TypeScript,
lint and protected production preview readback accompany the fix.

## Session composer without keyboard footer (0.8.74; roadmap0.8.46)

The remaining idle keyboard hint is removed from the shared project/skill
session composer. Its paragraph leaves no empty row. Keyboard handlers, Send,
queue/direct delivery, IME handling, attachments, errors and recovery controls
retain their existing behavior. The shared hint style remains in use for
functional attachment guidance.

Source/diff review, targeted sight checks at1440/320px with an existing preview,
Studio build, TypeScript and lint verify this text removal. No new tests or
browser fixtures and no model calls, Send, Play or VM actions are used.

## Own Desktop window controls (0.8.73; roadmap0.8.3)

New project sessions expose **Control app window** in the VM tool permissions.
The tool resizes the client area, minimizes or restores only the live Desktop
app launched by that session. Enable the permission and pass `windowControl=true`
to `studio_run_project` with a newly deployed helper. The original DESKRUN launch
delegates to its actual generation-bound watchdog. Ordinary runs retain their
previous command budget; delegated launches include the full controller option
in the existing112-byte SSH limit and reject oversized commands before starting.

The adapter uses SDK0.64.127 / Contract0.64.68's native Desktop actions. An exact
broker epoch, original launch request, process generation, window incarnation and
grant bind each command. Studio saves the complete native request, deadline and
operation ID before submission. A lost native result triggers Status for that
same operation. Applied and Current states and fresh composed-frame confirmation
remain distinct; unconfirmed actions prevent new commands and old-image input.
A scope-only status cannot replace an outstanding operation's receipt.

Existing sessions preserve their original dynamic tool declarations; create a
new session to use this new tool. Old deployments and guests without the native
delegation return a concrete limitation. No other session, foreign window, global
WM action or automatic app relaunch is exposed. Capture a new image after a
window action before further input. Native frame confirmation is separate from
an agent's visual assessment or the configured app checks.

Qualification used an isolated Full0.88.107 / Kernel0.1.452 guest: client resize to
640×400, minimize/restore, deliberately discarded native restore reply, a button
click changing state42 to43 in the same app, tampered request rejection and a real
reused GUI slot protected from an ended controller. Current sources and actual
native frame/geometry receipts accompany the screenshots. Settings were checked
at1440/320px for both new and preserved legacy sessions. Targeted host tests,
private helper builds, Studio build, TypeScript and lint accompany the evidence.
Environment guidance now describes the installed native capabilities and keeps
project-specific pins, compiler availability and outside-client capture limits
explicit. User projects, sessions, defaults and VM processes remain preserved.

## Retained Desktop completion (0.8.72; roadmap0.8.1)

New deployments build their private helper with SDK0.64.127 and its exact
Contract0.64.68. DESKRUN's original request and 192-bit service epoch bind an
independent WINSVC evidence lease before Desktop's launch reference expires.
Studio durably saves the receiver intent, reservation serial and canonical
process token before Offer/ACK. Lost RPC replies are reconciled by Status for
that same intent; no replacement app or independent retain is submitted.

The helper reads the retained actual exit code, completion sequence and output
of that process generation after Desktop cleanup. Native output flags preserve
empty, truncated and incomplete results. Exit status, output completeness,
process end, helper cleanup and visual checks remain separate. Old deployments
retain their original helpers and conservative behavior; an unavailable or
stale lease never supplies an inferred exit code or a passing text criterion.

Explicit job recovery can run a fresh reader of an acknowledged saved token
only after checking the original VM/boot, deployment and helper bytes. It copies
output atomically, keeps the previous captured stream and writes a separate
completion receipt. This does not claim helper cleanup or replay the app.
The last native reference is released after the host has durable evidence.
Run and Test describes these capabilities as conditional until the assigned
guest confirms the actual handoff.

Qualification uses SDK0.64.127 / Contract0.64.68 / Full0.88.107 with Kernel0.1.452
in a separate KVM guest. Six native cases cover fast C exit37, Rust App.write
exit29, zero output, a truncated131072-byte write, intentionally discarded
Offer/ACK replies, a fresh saved-token reader, stale epochs and explicit release.
Targeted host checks, helper builds, Studio build, TypeScript and lint accompany
the native evidence. User projects, sessions, pins and VM processes are preserved.

## Automatic VM host keys (0.8.71)

VM Settings no longer offers **Verify a new host key**. After a release change
or system reset, the first authorized SSH connection already authenticates the
guest and binds its new host key to that VM, image and system generation.
**Save access** is unnecessary for this automatic binding. The fingerprint,
**Enable SSH access** and **Check access** remain available. A changed key for
an unchanged VM/image/system binding still fails verification.

The four existing VMs were checked through the normal development coordinator:
all authenticated with distinct current host keys and reported R4OS0.88.107 /
Kernel0.1.452, without a manual trust reset or VM restart. Only the redundant
UI control was removed; transport behavior and compatibility API are unchanged.
Build, TypeScript, lint and source review are used; no tests or fixtures are run.

## SDK release metadata compatibility (0.8.70)

Published SDK sets can omit the redundant component `source_url` when they
declare an exact source commit. Studio derives the canonical official repository
URL from that commit; an explicitly contradictory URL is still rejected.
Archive names, release URLs, prefixes, byte counts, SHA-256 values, package
versions and the SDK's exact Contract pin retain their checks.

The capability catalog supports both the original nested `package` metadata and
the direct `file`/`bytes`/`sha256` layout published with SDK0.64.127. The direct
asset URL is derived within the selected official SDK release. Conflicting
metadata, cross-release URLs, invalid names/digests and oversized JSON are
rejected. SDK selection, Zig/C project tools, SDK Rust download and existing Rust
pins share the same interpretation; original manifest bytes/hashes are retained.

The actual published SDK, Contract, Libraries, HostTools and capability assets
were read and checked against the release manifest and checksum list. No SDK
code, model calls or tests were run. Existing defaults and project pins are
preserved; **Check for updates** refreshes the SDK catalog before the user chooses
a download or default separately.

## Continue native transport timeouts (0.8.69)

New compatible Codex/API runs also continue the exact observed native
`stream disconnected before completion: Transport error: timeout` failure.
The existing60-second delay, five additional attempts without model progress,
original worker/thread, confirmed tools, Goal/Live-Play and control gates apply.
A specific safe message explains the timeout; no HTTP status is invented.

New captures freeze stream retry protocol2. Their complete failed-turn evidence
reader remains bounded at32MiB total,2MiB per record and65,536 records, covering
the observed8.9MB turn and865KB context checkpoint. Every original ordinal and
paired call/result is still required. Saved version1 queues keep decoding-only
recovery and their previous reader limits; HTTP recovery is unchanged. No old
worker or failed run is restarted. No tests, fixtures, model calls or failure
simulations are run for this extension, as requested. Static checks and details:
[Provider-Retries.md](Provider-Retries.md).
An initial admission hold caused by an unconfirmed tool result or possible
partial changes now names that reason in the safe session error.

## Continue response-body decoding failures (0.8.68)

Compatible new Codex/API runs can continue the exact observed native
`network error: error decoding response body` failure in their original worker
and thread. Ordinary responses, GOAL and Live-Goal use the existing60-second
delay and at most five additional attempts without model progress. Completed
tool results remain in the conversation. Pause/Stop, queued input, changed
rights, limits and unconfirmed effects retain priority.

The new capability is frozen for new runs; saved queues, already running workers
and failed runs retain their previous behavior. GOAL checks the complete original
failed turn, including a known completed remote context checkpoint with paired
calls. No old prompt or tool result is submitted again. The specific failure has
a safe English message and a nullable HTTP status. No tests or model calls were
run for this extension, as explicitly requested; syntax/Build/TypeScript/Lint and
source review were used. Details: [Provider-Retries.md](Provider-Retries.md).

## Use sent attachments as project files (0.8.67)

New runs expose already sent attachment originals read-only under
`/attachments/<attachment UUID>.<png|jpg|webp|txt|pdf>` in the existing tool
sandbox. With **Run command**, **Read attachment** and **Read file** enabled,
the agent can verify the hash and copy a requested texture into `assets/`
using the normal terminal. Existing conversations can use prior sent files
on their next explicit message; no upload or new session is needed.

Access freezes the exact accepted owner/session references, validates original
bytes and requires the active run's workspace lease. Unsent uploads, other
sessions, credentials and host paths stay outside the namespace. No file is
automatically copied or executed. Already admitted workers and old queued
captures keep their original access; a new queue keeps its original file set.
The existing tools, native profiles and SDK/project pins remain unchanged.

## Simple session deletion confirmation (0.8.66)

Session settings → Delete session now asks **Are you sure?**, with **Yes** and
**No** and no name field. No preserves the settings draft. Yes submits the
current preview's session identity and revision through the existing deletion
API. Active/unconfirmed work and original receipt recovery retain their checks.

## Attachment validation in the web service (0.8.65)

Production image/PDF uploads now use the existing unprivileged agent coordinator
for the fixed, networkless decoder. The web service retains all its hardening;
`RestrictSUIDSGID` and `ProtectKernelTunables` otherwise prevent Bubblewrap from
starting there. Delegation accepts only a registered owner/session and pending
attachment ID, verifies the original byte count/SHA-256 before and after decoding,
and runs one validation at a time within the coordinator's memory budget.
It accepts no paths or commands.
An unavailable coordinator has a service error and no local fallback. Standalone
development keeps the direct isolated decoder. File limits, qualified decoders,
original receipts and explicit Send behavior remain unchanged. A protected
production-mode HTTP test accepted the user's unmodified 32×32 palette PNG and
an owned PDF, retained receipts and rejected truncated/unavailable-service cases.

## Session deletion after Stop (0.8.64)

Deletion preview, confirmed admission and original cleanup now wait up to two
seconds for short status/history reads to release the session lifetime gate.
A stopped session no longer immediately reports “This session is in use” when
the confirmation opens during a brief read. The name field becomes available
after a successful preview. Active workers, pending or unknown effects, changed
scope/revision and incorrect names retain their existing rejection rules;
no lock is forced and no deletion request or tool effect is replayed.

## Session stream shutdown (0.8.63)

Closing or backpressured session event streams no longer write a later
heartbeat or resume output after an asynchronous read. Response errors are
handled locally, and stream/timer cleanup is idempotent. This prevents a
disconnected session stream from crashing the web service and its private VM
bridge. Event cursors, replay/live delivery and ongoing agents/VMs retain their
existing behavior. Details and targeted regression coverage:
[Session-Text-Streaming.md](Session-Text-Streaming.md).

## Provider recovery (0.8.61)

Compatible new Codex/API and Claude subscription runs can continue qualified
502/503/504 failures in the original worker after60seconds, up to five additional
attempts. Original tools, Goal/Live-Play and active-time accounting are retained.
Pause/Stop, queued input, changed rights, limits and unknown outcomes take
priority. Old runs and queued configurations remain unchanged; reload/recovery
never starts inference. Details and verification limits:
[Provider-Retries.md](Provider-Retries.md).

## GOAL for API providers (0.8.60)

API sessions now support native GOAL Save/Play, live activation, Pause/Stop and
status readback. Saving and checking status need no API credential or model
request. Explicit Play keeps the original API lease, thread, permissions and
selected effort. Existing snapshots remain unchanged; older coordinators keep
the controls unavailable. Details and remaining retry scope:
[API-Goals.md](API-Goals.md).

## Claude GOAL admission after a completed step (0.8.59)

If fresh subscription admission refuses a later Goal input, the worker now
retains the preceding confirmed Goal result and its exact input identity.
Matching closure/history evidence ends the Goal as Blocked, or Paused after
Pause/Stop, without another input or an unnecessary native interrupt. Missing
or contradictory evidence and uncertain effects still retain Unknown.
Details and verification limits: [Claude-Live-Goal.md](Claude-Live-Goal.md).

## Claude follow-ups after the current response (0.8.58)

Claude sessions show **After response** for Ctrl+Enter while a compatible response
runs. The saved input keeps that exact response/session target, waits for its
confirmed end and then resumes the same native conversation with fresh admission.
Reload reads its original receipt. Stop and explicit Goal Pause hold the queue;
Continue is a separate human action. Unknown outcomes retain their protection.
Details and remaining retry/lifecycle scope: [Claude-Queue.md](Claude-Queue.md).

## Live Claude Studio GOAL (0.8.57)

Compatible new Claude workers accept Save/Play during an ordinary response.
Play waits for that response, then starts the saved bounded Goal in the same
query with a separate native input and fresh subscription admission. Its clock
excludes the original response. Queue priority, original-worker Pause/Stop and
passive recovery preserve original effects and request identities. The actual
connected Pro path and controlled native refusal were checked in owned sessions.
Details and remaining lifecycle scope: [Claude-Live-Goal.md](Claude-Live-Goal.md).

## Claude document and image inputs (0.8.55)

Claude now receives ordered attachment content with original native input
receipts. Documents retain explicit extraction/provenance; qualified native models
accepts actual PNG/JPEG/WebP image blocks (4 MiB each,8 MiB per send). Read the
native model catalog again to enable the qualified image capability. Existing
catalogs keep their prior image status. System/project/skill
sources are hash-bound snapshots, and skills use the permitted Studio broker.
Missing or changed content is refused without losing uploads or replaying work.
Details: [Claude-Inputs.md](Claude-Inputs.md).

## Claude provider removal and auth recovery (0.8.54)

Disconnect a Claude subscription before using **Remove provider**, then type its
exact display name. Removal checks native status, invokes native logout and
confirms the resulting status in that provider's private home. Active or
unconfirmed worker leases block changes. Conversations and original receipts
stay on the host; old creation/auth requests cannot recreate the connection.
Lost replies are recovered by reading the original request. Cancelled or expired
authentication requires an explicit status check before another auth change.
Details: [Claude-Authentication.md](Claude-Authentication.md).

## Claude account holds and model errors (0.8.53)

Native subscription rejection or extra-usage events stop further admitted work,
hold the account's queues and preserve original tool/result evidence. Active
workers also observe shared account holds. Fresh metadata and reset clocks
never resume work; a new explicit send, queue continuation or initial Play must
pass fresh admission. The session quota view exposes the hold and original
quota sources. Typed native model/auth errors use fixed safe text, and a late
Stop preserves an already completed result. Native automatic retry/fallback
paths are disabled where supported; the pinned CLI retains its documented
same-model streaming-404 negotiation. Details: [Claude-Limits.md](Claude-Limits.md).

## Claude text session selection (0.8.52)

Connected Claude subscriptions can use fixed native model IDs in new project
and skill sessions after a fresh model-catalog read. Native default reasoning
is a valid selection, and Claude creation checks its own runtime independently
of Codex. Each send still requires fresh native subscription/usage admission
with paid extra usage disabled. New original text inputs require a matching
native receipt before Studio tool effects. Image/context capabilities remain
unknown; unqualified attachments and extras are refused. Existing provider
records and the installed SDK profile remain compatible and unchanged.
Details: [Claude-Models.md](Claude-Models.md).

## Provider dialogs on HTTP LAN origins (0.8.51)

Claude provider creation and authentication, and API provider mutations, now
generate request UUIDs with browser `crypto.getRandomValues`. These flows also
work on the Studio HTTP LAN origin where `crypto.randomUUID` is unavailable.
Original request IDs are still stored before sending and retained for recovery.

## Claude final output statistics (0.8.50)

Confirmed final stream counters now add per-response output and matching totals
to session/project/lifetime statistics. Separate immutable receipts preserve
existing input counts, deduplicate resumed responses and survive scoped session
cleanup. Missing/interrupted measurements remain unknown with partial coverage;
assistant placeholders, cumulative session values and quota are not substituted.
Actual account acceptance remains deferred by the user. Details:
[Claude-Input-Usage.md](Claude-Input-Usage.md).

## Claude GOAL controls and queue priority (0.8.49, partial)

Project and skill Goal controls now support provider-specific local Save,
native-confirmed Play, Pause after the admitted step and immediate Stop.
Queued messages take priority at the step boundary and resume the same native
conversation after confirmed closure. The UI shows the eight-step/15-active-
minute bounds; unknown tokens and Codex thread identity remain null. Live
activation during an ordinary Claude response remains open. Actual account
acceptance is deferred by the user and public model admission stays gated.
Details: [Claude-Goal.md](Claude-Goal.md).

## Bounded Claude GOAL engine (0.8.48, private)

A separate Studio execution ledger qualifies up to eight Claude steps and 900
active seconds under one original Play. Every continuation needs native input,
progress and result receipts, confirmed tool outcomes and fresh subscription
admission. Automatic provenance stays in the Studio ledger; no Codex Goal RPC or
new human authority is invented. The control adapter is extended in0.8.49;
public model admission and real account acceptance remain open. Details:
[Claude-Goal.md](Claude-Goal.md).

## Claude queued follow-ups (0.8.47)

Claude text follow-ups use the common queue, unchanged frozen selection and
same native session after the original worker closes. Acceptance requires an
actual native input receipt; local submission and metadata tags do not qualify.
Stop/Unknown, changed bindings and coordinator recovery hold further dispatch.
Direct steering/retry, GOAL and actual account acceptance remain open. Public
model admission stays gated. Details: [Claude-Queue.md](Claude-Queue.md).

## Claude input/cache statistics (0.8.46)

Completed native response IDs now feed confirmed Claude input/cache counters
into session/project/lifetime statistics without double-counting replayed or
parallel blocks. Output and total counts remain unknown. Public model admission
and actual subscription acceptance stay gated. Details:
[Claude-Input-Usage.md](Claude-Input-Usage.md).

## Original-worker provider continuations (0.8.45)

New compatible ordinary-answer workers retain their original thread and empty
input while retrying confirmed pre-response HTTP502/503/504 failures. Five extra
attempts,60-second durable waits, current admission/receipt checks and shared
countdown UI are implemented. Active GOAL recovery and positive integrated
runtime acceptance remain open; no synthetic retries, inference or user actions
were run. Details: [Provider-Retries.md](Provider-Retries.md).
API context metadata is now frozen before lease reservation; workers preserve
older frozen API snapshots rather than changing their admission hash.

## Violet Goal STOP (0.8.44)

Pressed GOAL STOP now uses the shared violet control styling in project and
skill sessions. Control behavior is unchanged. Details:
[Session-Composer.md](Session-Composer.md).

## Compact development receipts (0.8.43)

New project sessions use v15 compact development results with explicit complete
detail/inventory/output reads. Paging, capture limits and presentation omissions
are distinct; existing profiles retain their declarations and full responses.
Details: [Compact-Development-Results.md](Compact-Development-Results.md).

## Bound Desktop argument budgets (0.8.42)

Run & Test and deployment receipts expose the canonical DESKRUN UTF-8 budget.
Oversize starts are rejected before admitting a new job, with no argument
shortening or retry. Details: [Desktop-Launch-Budget.md](Desktop-Launch-Budget.md).

## Diagnostic own-window screenshots (0.8.41)

Fully bound visible/focused Desktop windows can be captured for diagnosis while
native content readiness remains unknown. These marked frames cannot authorize
GUI input, visual checks or completion. Details:
[Diagnostic-Window-Captures.md](Diagnostic-Window-Captures.md).

## Live output-file criteria (0.8.40)

New workers expose bounded, generation-bound observations of registered output
files while an application runs. Explicit completion still performs a fresh
preflight and owns closing/cleanup. Details: [Live-Output-Files.md](Live-Output-Files.md).

## Stored uploads icon (0.8.39)

Saved files and pending cleanup now expose the existing upload dialog through
a conditional icon beside Attach files. Confirmed empty sessions have no extra
row; the paperclip is optically centered. Details:
[Session-Composer.md](Session-Composer.md).

## Goal and model layout (0.8.38)

GOAL, centered controls and stacked status/runtime now occupy the first card
row, with the centered objective below. Model choices have a matching frame.
Existing Goal/clock/model behavior is retained. Details:
[Session-Composer.md](Session-Composer.md).

## Subversion roadmap cards (0.8.37)

Collapsible cards now put saved status and task/acceptance progress in their
headers, with distinct content/action sections and separate reorder controls.
Cleanup history remains last. Details: [Roadmap-View.md](Roadmap-View.md).

## Direct roadmap export (0.8.36)

The main-version download icon starts the existing immutable saved-version
download directly. Original-request and confirmed-snapshot recovery stay
internal; success adds no details panel or extra link. Details:
[Roadmap-View.md](Roadmap-View.md).

## Main roadmap card and navigation (0.8.35)

The header now combines project name and Roadmap. A separate main-version card
places progress beside metadata, with full-width closed Vision/Version notes
sections. Version navigation uses two lines with accessible full titles.
Existing draft/save/recovery behavior is retained. Details:
[Roadmap-View.md](Roadmap-View.md).

## Project GitHub Issues (0.8.34)

GitHub now has Connection and Issues in column three, with a separate open-issue
total. The read-only list supports Open/Closed/All and paging; its total excludes
pull requests and distinguishes confirmed zero from unavailable data. Bound
account/repository checks, safe links, preserved Connection drafts and scope-aware
reads keep existing project workflows intact. Details: [GitHub-Issues.md](GitHub-Issues.md).

## Preferred roadmap order (0.8.33)

The versioned runtime contract now includes the user's approved wording:

> Prefer working through roadmap subversions in order, starting with the earliest open subversion. Whenever practical, finish its implementation and required checks before moving on. If a blocker or dependency makes this impractical, you may continue with independent work in a later subversion. Briefly document the reason, keep unfinished items open, and return to them when progress becomes possible. Explicit user priorities take precedence.

New compatible project runs with Roadmap on, including resume, receive this
guidance through the existing composition. It adds no ordering lock, status
change, confirmation or tool permission; the conditional publication rule from
0.8.32 remains in force. Saved prompts, native threads and running workers stay
intact. Source/composition and static checks qualify this text-only change; no
new tests, browser fixtures or model inference were used.

## Checked roadmap milestone publication (0.8.32)

The runtime roadmap contract now instructs project agents to commit/push each
finished, checked subversion when Roadmap, a confirmed repository and frozen
Push permission are present. Original receipts and frozen target checks keep
publication, no-change and unknown outcomes distinct. Saved prompts and existing
workers remain intact. Details: [Roadmap-Publication.md](Roadmap-Publication.md).

## Supported tool defaults and corrected settings (0.8.31)

New compatible sessions default supported tools on, including update commit and
rollback; Push additionally needs a confirmed repository binding. Existing saved
choices and runs stay intact. Environment note and native image operations now
use their real grouped switches without duplicate disabled Files checkboxes.
Details: [Session-Tool-Defaults.md](Session-Tool-Defaults.md).

## Immediate local project navigation (0.8.30)

Project navigation and local content no longer wait for GitHub. A bounded
background check shares its original job, preserves drafts and offers the
existing protected Update/Ignore choice for confirmed changes. Warm session
lists are retained and revalidated. Details: [Project-Opening.md](Project-Opening.md).

## Smooth live assistant text (0.8.29)

New assistant replies now reveal complete Unicode characters with a short violet
writing edge. Canonical input remains immediate; history/replay, completion,
Reduced Motion and large bursts display directly. Markdown, selection, code
copy, images and manual scrolling retain their existing behavior. Details:
[Session-Text-Streaming.md](Session-Text-Streaming.md).

## Live screenshot gallery (0.8.28)

The open gallery now follows new saved captures automatically. Historical
selection and scroll position stay fixed; hidden/closed views stop reads and
release image resources. Only visible/nearby previews load, with three image
requests at most. Authentication, scope changes and missing-image retries
preserve the original evidence. Details: [Screenshot-Gallery.md](Screenshot-Gallery.md).

## Screenshot gallery overlay (0.8.27)

The session header now opens a gallery beside Statistics: a large latest image,
horizontal older-image strip, paging and explicit Latest/held selection.
Close/Escape/focus, run Stop and distinct loading/empty/missing/auth states work
on narrow screens. The composer draft stays intact. Details:
[Screenshot-Gallery.md](Screenshot-Gallery.md). Automatic observation is implemented in 0.8.28.

## Session screenshot catalog (0.8.26)

Protected session reads can now page through registered agent VM captures across
all runs/jobs. The bounded reference index preserves original PNGs, verifies
tool provenance and reports incomplete/unclear legacy coverage. Image reads
check exact membership and original bytes; listing never captures again.
Details: [Screenshot-Gallery.md](Screenshot-Gallery.md). The overlay follows next.

## Session context speedometer (0.8.25)

Model now has a compact violet context meter beside it. It pulses above 50%,
respects Reduced Motion and provides measured token/source details on hover,
focus or touch, including while model selection is disabled. Unknown data
stays explicit. Details: [Session-Context.md](Session-Context.md).

## Session context data (0.8.24)

Protected session reads/events now retain the last native context measurement,
effective window, actual model/source and freshness. Cumulative consumption is
kept separate. Compaction/selection changes and older/unqualified workers show
explicit pending/stale/unavailable states. Details: [Session-Context.md](Session-Context.md).
The visual indicator is implemented in 0.8.25.

## Native Claude lifecycle guards (0.8.23, partial implementation)

Original Stop/results and explicit resume, fresh native subscription/extra-usage
admission, verified-account holds, canonical model/effort binding and private
deduplicated usage snapshots are implemented. Public model execution, GOAL,
queue and complete usage/lifetime accounting remain unavailable pending their
qualification. Synthetic native protocol checks do not replace real account
acceptance. Details: [Claude-Lifecycle.md](Claude-Lifecycle.md).

## Native Claude model metadata (0.8.22, partial implementation)

The provider can now read/cache native model identifiers, resolved aliases and
effort choices with the original account-bound metadata receipt. Context/image
facts stay unknown; Fast Mode and model execution remain unavailable pending
qualification. Existing engine/provider boundaries stay fixed and unqualified
screenshot delivery produces an explicit notice. Details:
[Claude-Models.md](Claude-Models.md).

## Native Claude subscription observations (0.8.21, partial acceptance)

Provider and compact session views now show native quota windows, remaining
percentages, local reset/countdown and explicit stale/unknown coverage.
Original protected metadata requests use the pinned native SDK with no model
prompt or token-based quota estimate. Actual isolated usage/warning protocols
and browser checks qualify these observations. Shared limit stopping and the
final overage/model/lifecycle gate remain open; model admission stays closed.
Details: [Claude-Limits.md](Claude-Limits.md).

## Native Claude sessions and Studio tools (0.8.20)

Persistent native project/skill workers now reuse the existing Studio tool
permissions and durable receipts through one private fixed MCP channel.
Original UUID/history/account/runtime bindings protect resume, compaction and
Stop; native builtin tools remain excluded. Isolated actual SDK/CLI protocol
checks cover text, tools, PNGs, large results and repeated-call deduplication.
Public model use still awaits the quota/overage and model/lifecycle stages.
Details: [Claude-Sessions.md](Claude-Sessions.md).

## Native Claude subscription sign-in (0.8.19, partial acceptance)

System → LLM Providers now offers a named Claude Pro/Max provider with native
Connect, code handoff, Cancel, timestamped Status, Reconnect and confirmed
Disconnect. Native credentials stay private per provider; original requests
recover without repeating sign-in. Existing OpenAI/API providers stay intact.

Model use remains disabled until the session/tool and limit/overage stages.
Actual empty-home network-isolated CLI checks and controlled auth/UI cases
qualify the integration; a real human subscription login and the final native
refresh/expiry/worker/queue acceptance remain open. Details:
[Claude-Authentication.md](Claude-Authentication.md).

## Native Claude Subscription foundation (0.8.18)

A distinct Claude-plan identity and immutable engine binding now prepare the
native Claude Code2.1.312 / Agent SDK0.3.312 adapter. Fixed official archives,
individual file hashes/integrity and original licenses are pinned; explicit
unprivileged setup publishes a private immutable runtime without npm/plugins,
latest updates, account login or model inference.

Coordinator metadata probes run with empty private filesystem/config/input,
no network and no tools. Native/session/message/tool IDs remain distinct,
unknown/error states never create a replacement conversation. Actual SDK,
adapter and restricted-service probes plus focused store/stream tests qualify
this foundation. Authentication, model turns, Studio tools, quota/overage,
model UI and Goal remain staged for19–23; existing OpenAI/API sessions retain
their original records and histories. Details: [Claude-Subscription.md](Claude-Subscription.md).

## API lifecycle and authoritative usage (0.8.17, partial)

API statistics now join original native response receipts to explicit provider
wire counters. Omitted subcounters stay unknown instead of inheriting native
zero defaults. Frozen provider/adapter/thread provenance stays private; existing
spend keys and subscription counts remain unchanged. API usage publishes after
original transport closure and deduplicates raw/history/restore observations.

Focused Node/Python and original-binary offline cases cover project/skill
instructions/rights, text functions, resume, queue/key rotation, unknown leases,
Stop, missing usage and provider/session deletion with retained lifetime totals.
Unsupported images/hosted extras/Goal stay explicit. No real model inference,
user guest action or new server/model installation is used.

0.8.17 remains open for the0.8.10 retry controller and final lifecycle acceptance.
Details: [API-Session-Lifecycle.md](API-Session-Lifecycle.md).

## Existing local/custom model servers (0.8.16)

Local API now offers explicit Ollama/LM Studio server contracts and local
address presets, optional bearer/no-auth, protocol and reverse-proxy prefixes.
The real host worker checks Models metadata only; no model/server installation,
download, loading or reconfiguration occurs. Exact manually declared model
capabilities and actual configured context are required for named servers.

Plain streamed text/function sessions preserve original native history,
acknowledged call receipts, queue snapshots and same-thread resume. Responses
is stateless for Ollama; LM Studio Responses/Chat use the qualified plain scope.
Reasoning/image/hosted extras remain visibly unavailable. Profile changes bind
new sessions; old records/threads and subscription accounts stay intact.

Eight original-binary offline worker cases, actual GET-only metadata helpers,
focused protocol/store/HTTP checks and browser1440/320 qualify these contracts
without real model inference. Build/TypeScript/lint and normal immutable release
verification apply. Details: [API-Local-Servers.md](API-Local-Servers.md).

## OpenRouter routing and qualified tool sessions (0.8.15)

OpenRouter now binds exact model/key and optional backend order/allowlist,
explicit gateway fallbacks and app attribution. All sent tool parameters must
be supported. Plain streamed Chat/function history uses the unchanged native
engine, original tool ledger and stateless same-thread resume. OpenRouter
reasoning tool-history/Responses and hosted extras are explicitly unavailable;
other API kinds retain their qualified protocols.

Run-bound notices distinguish the requested model from reported model/backend,
endpoint labels and provider/local response IDs. Missing origin/usage stays
unknown. Key/account/access/rate/temporary errors are precise; no automatic
retry, model/provider switch or inference on Save/open is introduced.

Two protocol/four policy groups, protected HTTP, owned TLS/DNS/metadata,
eight actual native project/skill/error/Stop/resume cases and browser1440/320
qualify the change. No real key or model inference is used; one public Models
metadata read validates the current schema. Required build/TypeScript/lint and
normal immutable release/user-data verification apply.
Details: [API-OpenRouter.md](API-OpenRouter.md).

## API connections, model catalogs and session choices (0.8.14)

System → Settings → LLM Provider now offers OpenRouter, Custom API and Local API
beside the existing ChatGPT subscription. Explicit Save/Cancel/Replace/Clear
keeps keys write-only. Save/open and new sessions do not send model requests.
Check connection reads one bounded Models API through a fixed, verified-TLS/
pinned-IP helper; original receipts, key rotation and confirmed transport exit
protect recovery/disconnect. Cache plus original receipt publish atomically.

Model source, limits and declared/effective capabilities are visible. Generic
IDs remain unknown; exact manual IDs and documented capabilities/efforts can be
configured without paid probes or copied OpenAI model defaults. Qualified facts
compile neutral descriptors for the unchanged pinned native engine. Project and
Skill New Session/settings/composer preserve fixed provider identity, missing
model values, original requests, message drafts and uploads. API-hosted web/image,
image input, Fast Mode and native Goal remain unavailable pending qualification.

Focused private-store/actual metadata-helper, TLS/DNS/bounds, protected HTTP,
original-native SQLite-catalog project/skill/Stop and browser1440/320 cases cover
the change, with build/TypeScript/lint. No real credentials, remote model calls,
inference, user agent/VM actions or component pin changes are required.
Details: [API-Model-Catalogs.md](API-Model-Catalogs.md).

## Native Chat Completions adapter (0.8.13)

Qualified Chat-Completions-only API models now use the same native0.163.0 agent,
original context, rights and Studio tool ledger through a bounded private wire
adapter. Instructions/text/function calls/results retain their original data and
IDs. SSE/UTF fragments and parallel arguments are collected safely; complete
validated calls are released only after an acknowledged stream finish. Restart,
native compaction, incomplete output, quota, Stop and deadline preserve original
receipts without another model/tool loop or automatic replay.

An explicit revision-bound internal model policy qualifies text/function stream,
context and plain/standard-effort reasoning before admission. Unsupported images,
opaque reasoning, hosted web/image/Fast/Goal semantics remain unavailable.
Provider/model discovery and UI follow later roadmap entries. Native private
telemetry stays local; transport IDs and reported provider IDs are separate.
Reported usage is mapped without inventing missing counters. A900s absolute
request deadline supplements checked-IP/TLS/redirect/header/body/stream limits.

Four grouped protocol cases, eleven store/capability cases, ten original-binary
offline worker cases and a Responses restart compatibility probe pass, plus
build/TypeScript/lint. No production provider/key, model inference, user session,
VM or pins changed. See [API-Chat-Completions.md](API-Chat-Completions.md).

## Native API Responses transport (0.8.12)

New API-bound project/skill sessions can use the unchanged Codex0.163.0 runtime
with a qualified revision-bound internal text-model catalog. A private run-owned
relay pins checked DNS addresses, verifies original TLS/SNI, rejects redirects
and bounds POST/SSE/error traffic. The real credential only enters that relay;
native receives a private unrelated nonce and tools retain their separate
network/credential-free namespace. Original Run/request/worker leases retain
credential revisions through rotation and refuse new claims after disconnect.
Queue cancellation and session deletion respect these original reservations.

Native sends full local history with store:false and no previous response ID;
stateful-capable endpoints use the same full-context mode. Studio items/deltas,
complete argument validation, rights and original call receipts stay in the
existing broker. Restart resumes the same thread; Stop, context rejection and
lost completion do not replay tool effects. Native retries, Responses Lite and
WebSockets are disabled for this provider. Hosted web/image/Fast/Goal capability
needs separate API-model qualification and is unavailable in these sessions.

Six original-binary offline Studio-worker fixtures, a core restart probe,
verified TLS/DNS/redirect/bounds checks, nine private-store cases and two existing
queue/deletion cases pass, plus build/TypeScript/lint. No real API/model inference,
production provider, user session/VM or pins changed. This is transport support;
provider/model UI and discovery remain later roadmap entries, and public
configuration still does not claim verified remote entitlement. See
[API-Responses.md](API-Responses.md) and [API-Providers.md](API-Providers.md).

## API connection and credential foundation (0.8.11)

Protected `/api/providers/api-connections` CRUD manages separate OpenRouter,
OpenAI-compatible and explicit local API records with canonical endpoint,
Responses/Chat Completions protocol, auth and distinct config/credential revisions.
Only keyConfigured is returned. Atomic private config/secret SQLite stores under
LLMProvider/ApiProviders use service ownership,0700/0600, DELETE journals/FULL,
protected paths and logical secret removal. Original request receipts and retired
IDs preserve safe recovery; origin changes require key replacement/removal.

Existing subscription providers/homes/threads are unchanged. Revision/lease
contracts preserve running original bindings; disconnect closes admission before
confirmed provider-worker cancellation. Unknown leases retain credentials.
Endpoint/network-scope validation rejects unsafe forms/targets; future transport
must pin checked DNS addresses, verify TLS and reject redirects. There is no HTTP
proxy or remote model request in this foundation. API connections explicitly say
runtime not-qualified and are not yet offered to native sessions. Actual transport
qualification stays open for0.8.12/13; settings/models/UI follow later entries.

Six isolated cases as r4os-studio plus one new/fourteen existing HTTP provider
cases pass. No real key, provider inference, production provider mutation or user
session/VM action. See API-Providers.md for operations, boundaries and open checks.

## Provider failure qualification (0.8.10, partial)

Project/skill workers now safely describe typed HTTP502/503/504 provider
failures, authentication/limits and stream failures, including a failed turn's
final error. Provider text/URLs/request identifiers stay private. A transient
candidate is diagnostic only; it does not authorize replay.

The five60-second automatic continuation attempts, durable countdown and
Goal/Queue/Stop/clock integration remain open. Native HTTP/stream retries stay
zero for the private image-capable provider to avoid uncertain image POST replay.
No Run is resumed, no new user message is inserted and no timer is enabled by
this release. `Provider-Retries.md` records the pinned native source/API findings,
continuation contract and remaining qualification. Source/AST checks and
Build/TypeScript/Lint only; no new tests/fixtures, user runs, VM actions or model
inference, as required by this roadmap entry.

## Host test C linker (0.8.9)

The tool/terminal sandbox resolves the existing host `cc` through a bounded
symlink chain to an executable under the public `/usr` tree. Only that validated
file is mounted read-only at private `/etc/alternatives/cc`; the rest of the host
alternatives and private `/etc` stay absent. A private `/host-tools/cc` PATH alias
makes the standard command available without pinning a GCC version. No host
alternative is repaired or changed and no compiler is downloaded. PATH omits
empty entries, including skill/non-Rust environments.

Missing, cyclic, non-executable or foreign alternatives use a small read-only
private diagnostic command that exits127. Other terminal and file tools remain
available. The worker's project-environment guidance states host-linker
availability. Host-only `rustc --test` remains separate from native R4X SDK builds;
keep project manifests, test scripts, Cargo.lock, compiler/SDK/Contract pins and
global defaults intact. A selected explicit public driver may be used for a
host-only diagnostic; it does not repair a missing native build capability.

Three isolated resolver cases and the real unprivileged sandbox verify the
standard/absolute cc paths, pinned Rust1.99.0 host test/link/exit0, non-Rust PATH,
unavailable diagnostic and unchanged256MiB hard file, read-only, credential and
network boundaries. No user project build, guest/agent run or model inference.

## Project folder activity (0.8.8)

The existing folder icon in the project list shows the chosen violet Energy
pulse while at least one project session is confirmed to be executing. Its
shape,17px/13px size and position stay fixed; no extra status icon is added.
Reduced motion uses a static highlight. The button exposes “Session running”.

The browser reads one protected `/api/projects/session-activity` aggregate every
five seconds while visible, and refreshes on focus, reconnect and run/Goal events.
Read failures clear the highlight; monotone expiry limits any sample to ten
seconds, including its request time. An older coordinator does not prevent normal
project navigation. No session or VM is started or stopped by this display.

The unprivileged agent coordinator reads registered ready-project IDs, only its
bound active-run records and indexed current run/Goal state through read-only
SQLite connections. One bounded systemd query verifies worker PID, birth, UID
and release. Queue/history/unknown flags, VMs and development jobs do not qualify.
Starting/running workers and stopping workers until actual exit qualify; an idle
paused/stopped Goal does not. No transcript scan, native RPC, recovery or data
migration occurs. Five isolated Python state cases, one protected HTTP case,
browser lifecycle/layout cases and Build/TypeScript/Lint cover this feature;
no provider inference or user session/VM action is used.

## Tool-call block width (0.8.7)

Shared project/skill transcript tool-call blocks are centered at80% width when
space permits. A34rem minimum capped at the available width keeps narrow chats
readable. Inner calls retain their full block width and existing expansion,
copy, status, scroll, job and image behavior. Other messages and the composer
retain their width. This is one outer CSS rule; no data or tool contract changes.

## Composer hint (0.8.6)

The named Queue/Send now keyboard hint is removed from the shared session
composer without an empty paragraph. Existing Enter/Ctrl+Enter/Shift+Enter
handlers, the separate idle hint and functional attachment/recovery messages
are preserved. This is a browser presentation change only.

## Total Goal runtime per session (0.8.5)

Project and Skill Manager **Session statistics** show **Total Goal runtime**.
This is the sum of recorded Play executions for exactly that owner/session,
including fresh current progress once. Pause/Stop, another Goal, reload and
multiple tabs preserve the sum. Queued/startup time, ordinary run prefixes and
confirmed pauses do not count. The current Play clock and existing global/project
longest-run records retain their meaning.

The session statistics response adds `totalGoalRuntime`: exact decimal-string
`durationMs`, a separately bound optional `live` clock and independent time
coverage. A read-only projection qualifies the private `goal_clocks`, original
activation/run bindings and canonical execution-keyed numeric receipts. Each
execution contributes only its greatest retained cumulative measurement across
local receipts, lifetime reconciliation and the pending outbox. Unmatched keys,
missing clocks/activations, partial restore and unknown segments remain visible;
neither native `timeUsedSeconds` nor UTC differences reconstruct elapsed time.

Live progress needs the exact current run, PID/birth, service UID, host boot and
fresh monotonic checkpoint. Stale/lost bindings freeze the confirmed base.
The browser interpolates only within that freshness window, and freezes on read
failure. BigInt formatting preserves sums and hours beyond24h. Token coverage
and time coverage are displayed separately.

New session creation records an additive `goal_time_coverage` marker in its
original transaction, allowing a confirmed zero before the first Goal. Original
threadless sessions and session-specific activation records provide qualified
legacy cases; a table belonging to another session is never evidence of zero.
No user history is migrated or remeasured. Missing legacy evidence is reported
as unavailable or partial. Session deletion removes the private marker/source;
confirmed numeric lifetime data remain under the existing deletion contract.

The browser only displays data; the unprivileged coordinator reads existing
measurements. Opening, polling and refreshing statistics cannot Play, stop,
launch a model or change a VM. Deterministic clock/source/restore/deletion,
owner-scoped HTTP and browser1440/320 checks use isolated fixtures only.

## Delete one session (0.8.4)

Project and Skill Manager Session settings include **Delete session** at the
lower left of every tab. A separate dialog requires the saved session name;
Cancel preserves settings and composer drafts. The server checks the session
revision and private scope again at admission. Active runs, executable queues,
pending/active/unknown Goals, uploads and unconfirmed tool/guest/remote/Git
effects prevent deletion. Confirmed original guest-end recovery is recognized.
Nothing is stopped automatically.

The unprivileged agent coordinator owns the deletion journal and cleanup. A
cross-process session lifetime gate covers admitted session use; other sessions
keep their own independent gates. An accepted request retires the selected
session, atomically detaches its private directory and removes its settings,
native/Studio history, runs/tool receipts, Goals, messages, attachments,
generated images, notes and worker scratch data. Linked/replaced or unconfirmed
targets are preserved with an explicit original-request recovery state.
Confirmed numeric statistics are reconciled first and remain in the lifetime
store. Project development artifacts/job receipts and project/skill sources,
shared components, provider credentials and VMs remain.

Read the original `/api/projects|skills/:owner/sessions/:session/deletion/:request`
receipt after a lost response. The browser keeps that request ID over reload;
only an explicit **Retry same request** resubmits it. Coordinator restart resumes
accepted cleanup without replaying any agent/tool/model operation. Minimal
text-free tombstones retain session/request identities and hashes; retired
creation requests return410 instead of recreating the session. Empty lifetime
lock files remain to prevent old open descriptors from bypassing the gate.

Confirmed deletion clears only matching browser caches and the selected route;
other tabs receive a session-scoped notification, with410 readback as fallback.
No new session is created. This is a browser-only action and is not an agent tool.
CSRF/owner/revision/scope, both owner types, crash recovery, numeric retention
and browser1440/320 checks use isolated fixtures without user-session deletion
or model inference. Existing hosts adopt the compatible coordinator normally;
no new privileged maintenance or bootstrap is required.

## Project environment qualification (0.8.3)

Agent runtime guidance includes the current project revision, language, role and
SDK/Contract/compiler pins. Original deployment pins and authenticated guest
evidence remain authoritative for older artifacts. The qualification in
[R4OS-Environment.md](R4OS-Environment.md) distinguishes C facade/raw enums and
window flags, observed Exchange naming limits, native capture/output retention,
host Rust builds and guest compiler/HTTP/TCP capabilities.
Session settings also recognize v14 in all inherited Build/VM/Updates/GitHub
capability hints, preserving the behavior of earlier profiles.

Own-window resize/minimize/restore remain unavailable pending a qualified native
contract. Legacy WINSVC record mutations are registry mirroring; their receipt
does not prove a Desktop window action. The newer generation-bound WindowMode
contract covers decorated/fullscreen mode, not these three operations. No global
input fallback, new tool/permission, guest helper change or pin update is added.
Roadmap0.8.3 completes source qualification and guidance only; mutating integration
and positive native action acceptance remain open.

## Bounded own-client GUI gestures (0.8.2)

New project sessions use additive tool profile `studio-tools-v14`. Existing
18 project/skill profiles retain their exact tool declarations and native threads.
`studio_send_vm_input` adds `kind=gesture`, a recent focused `frameId` and
1–32 `steps`: `phase=down|move|up`, client `x/y`, and monotonic
`atMilliseconds=0..2000`. Down/up explicitly select `button=left|right`;
every press must be released inside the same call. Moves without a press are
hover; timed down/up pairs form a double click. Deploy again to obtain a
`gestureVersion:1` helper. Old helpers/profiles fail before input.

The independent guest watchdog advances the bounded plan, validates the exact
process/window/focus/geometry and records its accepted prefix and actual enqueue
times. Stop, changed scope, deadline or disappearance of the exact native SSH
relay aborts remaining steps and enqueues release only for its own pressed
button. The relay supplies its own generation identity; callers cannot select
that identity. Failed release remains unconfirmed. No button hold spans tool
calls, and no global physical input or outside-client pointer capture is added.

Results include `gestureId`, `accepted/expected/complete`,
`queuedAtMilliseconds`, `abortedReason`, `releaseQueued` and
`consumptionConfirmed:false`. A receipt attests enqueue, not one-to-one delivery
or app consumption: the guest may coalesce intermediate moves. Partial/lost
results are never replayed automatically; original action receipts remain readable.
Optional 1-based `observeAfterStep` records one intermediate image and additionally
requires Capture VM permission and an image-capable model. It captures an
observed interval, not a guaranteed exact scheduled phase. Image bytes stay
transient; immutable job-bound image references and hashes are retained.

Nine isolated guest cases on Full0.87.14/Kernel0.1.384 qualify hover, drag,
right click, double click, the32-step boundary, wrong window/geometry, Stop,
focus loss and relay loss. Images and app-written logs distinguish actual app
effects from enqueue receipts. All testing uses a separate disposable VM;
no user project, VM, SDK/Contract pin or model inference is needed.

Existing hosts explicitly prepare only the updater compatibility ceiling with
`python3 scripts/agent-sessions/install-gesture-support.py` as root from App/,
then install the immutable release through Studio Updates. This preserves the
existing bootstrap, configuration, old rollback profiles, running workers and
VMs. No downloaded privileged installer is run. Outside-client capture remains
an independent native R4OS contract/qualification question.

## Desktop execution evidence (0.8.1)

Development job reads now include `executionEvidence`, derived without mutation
from matching private execution/boot/process-generation receipts. Process end,
helper cleanup, native exit status and completeness of captured process-console
bytes are independent findings. Missing or damaged originals remain unconfirmed;
zero captured bytes alone do not establish a complete empty stream. Existing
job states, checks, recovery guards and original histories are preserved.

Every received output frame is flushed before its bound observation and byte/hash
receipt are atomically saved, before another poll advances the guest cursor.
This preserves available evidence if the observer loses its later response. An
observation does not attest helper cleanup or authorize replay. New helpers mark
failed/inconsistent console reads incomplete and distinguish console observations
from native completion observations; existing deployed helpers remain readable.

Run & Test and the agent runtime explain the unconfirmed native Desktop exit
retention and application-output routing, including Rust `App.write`, before
criteria are selected. Configured exit/text criteria remain in place and cannot
pass on missing evidence. Job cards show lifecycle, cleanup, exit and console
findings beside the original checks and images. Desktop retains reap ownership.
SDK/Contract/helper pins and project pins are unchanged.

The native contract only exposes output from an **unconsumed** completion. A
retention guarantee after Desktop cleanup and full C/Rust application-output
routing have not been established. Roadmap0.8.1 therefore keeps its native
integration and positive guest acceptance open; local receipt checks are not a
replacement for those guest proofs. No production project was launched for QA.

## New Project recovery after a deleted GitHub setup (0.7.25)


## Native history without an image file limit (0.7.27)

Native Codex history includes screenshots and grows across turns. The former
image-generation `prlimit --fsize=67108864:67108864` also limited that history:
a long conversation could terminate its native process at exactly 64 MiB and
leave a partial JSONL record. Native Codex now raises only its own file-size soft
limit to the inherited hard limit; the image-specific history-size rejection and
64 MiB process wrapper are removed. Native tool declarations, thread identity,
project pins and image-generation choices are unchanged.

New host installations use `LimitFSIZE=268435456:infinity` for run units. Existing
hosts can apply only the additive override with
`python3 scripts/agent-sessions/install-native-history-support.py` as root from
App/. It reloads unit definitions without restarting services, agent workers or
VMs. New native processes then have no fixed per-file history limit. On an older
host without maintenance, its existing hard limit still applies. Every project
file/terminal sandbox separately enforces the previous 256 MiB hard file limit;
image dimensions, byte/count/storage checks and converter limits remain in place.
Already running workers retain their original release and resource settings.

Recovery must back up the stopped session before any change. Do not truncate,
reset or invent native history, mark an interrupted turn successful, or replay a
Tool call. For the affected Minecraft Main session the final screenshot already
had a completed native event and matching SQLite projection. Its complete output
matched all 21,694 retained bytes of the partial record; appending only its missing
4,614-byte suffix preserved every original history byte and image SHA-256. Goal
status is reconciled separately; continuing inference requires deliberate Play.

No tests, browser fixtures or model inference were run for this fix, as requested.
Production build/TypeScript and lint provide static validation. Private backups,
original receipt comparisons and recovery evidence remain outside this repository.


## Concurrent agent runs and preserved admission errors (0.7.26)

New host installations allow 16 concurrent agent runs. Existing installations retain
an explicit `maxActiveRuns` in `/etc/r4os-studio-agents/config.json`; ordinary updates
and rerunning the installer preserve that choice. Change only this positive integer
for explicit host maintenance, then restart the independent
`r4os-studio-agents.service` coordinator to load it. Existing run units keep their
original worker release and process; do not restart them or VMs for this change.
Admission and queued dispatch share the same limit. One run per workspace and
individual worker resource limits still apply. This concurrency limit does not
limit session duration or the lifetime number of runs.

Capacity exhaustion returns HTTP 429 with the configured limit before admitting a
run. The composer preserves the original submission error alongside its immutable
request and draft, including across reload. Status polling starts after submission
has returned; a missing receipt cannot overwrite the capacity error. Older pending
requests with no receipt explain how to use **Retry same request**. Recovery reads
never automatically submit a message or start inference; explicit retry keeps the
original request ID and input. Newer draft edits and attachment selections remain
preserved.

No tests, browser fixtures or agent inference were run for this hotfix, as requested.
Production build/TypeScript and lint provide static validation.

New Project now reads the status of a retained original creation request when
the dialog opens. A confirmed deleted project releases only that browser request
and its cached account, then resets the form to a blank local project. A late
Retry receiving HTTP410 uses the same reset. Previously GitHub-backed requests
kept their frozen input after deletion, leaving every reopening stuck on Retry.
Deleted projects and repositories are never recreated by the status check.

The session-protected `GET /api/projects/creation-requests/:requestId` distinguishes
missing, pending, complete, deleting and deleted local creation receipts. It
does not submit creation or GitHub work. A recovered existing project restores
its Open local project action and reads only the original GitHub job; confirmed
GitHub failure re-enables its connection/repository controls. Missing receipts,
active/deleting requests, unknown GitHub outcomes and failed status reads retain
the original request. Cancel alone still preserves an uncertain submission.

The change requires no catalog migration or browser-storage reset. Existing
deleted-request tombstones remain authoritative and the next loaded dialog can
recover an old saved request. Validation uses an isolated HTTP/SQLite case and
focused browser scenarios with synthetic GitHub replies; no real repositories,
connections, user projects or VM state are changed for testing.

## Historical development recovery context (0.7.24)

Goal continuation now includes the actual development job ID and its current,
owner-bound state beside historical unknown run/tool references. Previously the
context listed only agent run/call IDs and described every old unknown as still
unconfirmed, even after the original execution had been reconciled. An agent
could repeatedly query a run ID as a job ID and block an otherwise healthy Goal.

The snapshot reads existing development storage without creating jobs or
replaying tools. Creation calls match their deterministic original request and
run; status reads match their referenced job. Project/session scope and job kind
are checked. A confirmed guest end is included only when the job's close marker
and recovery metadata match its committed recovery receipt. Missing, damaged or
foreign evidence keeps the warning. Skill sessions never read project jobs.
Only bounded IDs, states and reconciliation fields are exposed; arguments,
credentials and raw tool output remain absent.

Current recovery guidance distinguishes agent run IDs from development job IDs,
historical unknown outcomes from a confirmed guest end, and status reads from
application starts. Later original job readback supersedes an earlier snapshot.
Confirmed closure permits new authorized work after inspection; it does not make
an inconclusive test successful or permit replay of the original call. Original
run/tool/job receipts and frozen old snapshots remain unchanged. The correction
applies at the next Goal Play, including existing native profiles and threads;
it does not resume a blocked Goal or restart a VM.

Three focused cases cover the two historical closure outcomes, incomplete or
foreign bindings, and existing unknown-write/no-replay protection. No provider
inference or guest application execution is used for validation.

## Run-message recovery and acceptance in0.7.5

Original message receipts remain available after their worker or native turn ends. Inbox revisions cover intake, dispatch and acknowledgement, preventing stale status responses from rolling the queue back. Unknown original inputs are retained and never retried; explicit Continue advances only separate unsent inputs. A later explicit ordinary Send starts a new chain after an empty earlier Stop hold.

Queue acceptance means Studio durably saved the input; direct acceptance means the native active turn accepted it, not that the model has finished acting on it. Check original request reads status. Retry same request uses the same durable identity and cannot repeat a possibly effective steer. Review rejected/unconfirmed originals before an intentional new submission. Stop/Pause hold later work; changed settings or frozen pins require review and explicit removal/resubmission. Live attachments use Queue message as a complete input. Existing Projects backup/restore retains the private journal and Ready attachments, while restore starts no model work. Skill sessions keep their existing separate backup boundary. The native/tool Unknown policy and original image-generation outcomes remain intact.

## Live composer and message queue in0.7.4

The composer stays editable during active runs and pending HTTP requests. Enter queues a complete input, Ctrl+Enter delivers text to the original active turn, and Shift+Enter inserts a newline. Idle Enter/Ctrl+Enter send normally. IME composition, repeated keys and other modifiers do not submit. Queue message and Send now expose the same actions, with an ordered queue, Remove for unsent entries and explicit Continue after a hold. Stop stays independent of a pending send.

A versioned draft and the exact original request are retained separately per session. Acknowledgement clears only the submitted draft version and attachment IDs; newer typing remains. Reload/reconnect reads original message or run receipts without automatic POST or inference. Rejected/unknown inputs remain available for explicit review and resubmission. Existing account/model controls, Goals and attachments are preserved. The actual browser fixture covers1440/320px, mouse/touch/keyboard, FIFO, Stop/Continue, response loss, reauthentication and multiple tabs without provider inference.

## Direct active-turn messages in0.7.3

The owning worker exposes a bounded private user-control socket with UID/PID/birth/release checks. Direct text uses native turn/steer with the original thread, expected turn and stable client message ID; it never starts a replacement turn. Durable intent precedes sending, RPC/native user-item receipts deduplicate visible messages, and uncertain outcomes are read back without retransmission. Stop or a changed target rejects new delivery. Live availability is reported only for the qualified runtime and an active native turn; old workers and live attachments remain explicit, preserving the full input for an intentional queue/send action. Accepted private user intents also retain verifiable human provenance. Browser keyboard controls follow0.7.4.

## FIFO message dispatch in0.7.2

Queued messages capture the same full settings, tool/skill selection, prompt, project pins and Ready attachments as run admission. The coordinator dispatches one original request at a time through the existing workspace/capacity checks. Stop, user Pause, failed/unknown predecessors and coordinator reconstruction hold the remaining queue until explicit Continue. A changed frozen selection preserves the message and holds dispatch; remove and submit it explicitly after reviewing settings. Native Goal continuation pauses at the confirmed turn boundary before user inputs take over; a racing continuation is interrupted before new tool admission. Queue controls remove only unsent entries and use revision-bound original receipts. Private upload bytes stay retained for accepted queued references. Direct live delivery and browser controls follow0.7.3/0.7.4.

## Session message intents in0.7.1

Private session SQLite now stores bounded user-message intents separately from run admission. Queue requests have stable IDs, atomic order and immutable payload hashes; readback is scoped to the project or skill session. HTTP mutations require the existing session/CSRF/Origin checks. Direct requests reject stale targets and workers without live-message support. This foundation does not dispatch the inbox yet; FIFO dispatch, native steering and composer controls follow in0.7.2–0.7.4. Codex0.163.0 steering fields were qualified with its schemas and original binary without provider credentials or inference. Existing tool profiles and native histories remain unchanged.

## Desktop launch command budget (0.6.57)

Desktop preflight now includes the complete DESKRUN command and R4OS SSHD's
15-byte `/NOAUTOEXEC /C ` Terminal wrapper in its 127-byte UTF-8 argument
budget. Checking only the DESKRUN argument tail missed that wrapper. A command
with `--world=F:\Build\PBF05AE8\D1FBF342\ABSENT` needed 130 bytes and SSHD
rejected it before running DESKRUN, leaving no native launch identity.

The launcher uses DESKRUN's native five-second default without the optional
`/WAIT:10000` flag; shorter execution deadlines retain an explicit wait.
The same example now uses 118 bytes including the wrapper. `/JSON`,
`/WAITFRAME`, the absolute target and literal application arguments remain.
Commands above 112 bytes fail before opening the guest controller or claiming
execution quarantine, with required/allowed byte counts and a clear diagnostic.
Arguments are never truncated and a launch is never retried. Actual transport
loss without an original launch identity still remains unknown.

Three focused regressions cover the original command, the exact UTF-8 buffer
boundary with short/default waits, and preservation of unknown transport
outcomes without replay. No user application or provider inference is started
for those tests. The correction applies to newly admitted development jobs;
running VMs do not need a different exporter. An old execution quarantine still
requires its original closure proof or a confirmed VM stop before reuse.

## Nested Exchange paths and live Goal controls (0.6.56)

Exchange now supports **16 path levels** beneath its root, including the Build,
project and deployment components. A valid world-save layout reached nine levels
and caused the previous six-level inventory to reject subsequent application
starts. The offline exporter and guest inventory use the same shared bound;
errors now distinguish excessive depth from case collisions and identify the
offending path. The 1 GiB/4096-file/1024-folder quotas remain. No saved generations
or diagnostic folders are deleted or flattened.

The running VM's immutable exporter must advertise the new depth. Stop/start it
with this release before further deployments. If an older exporter refuses an
existing deep tree on stop, keep its image and use **Retry exchange sync** with
the new web release while stopped, then start the VM. Do not edit release pins
or the live image. Normal conflict and recovery rules still apply.

Goal Pause/Stop/Save also now validate their live worker through the session
module's process identity helper. The coordinator previously imported that
helper from a development module absent from its own Python search path, so the
Goal command failed before reaching the worker and the run continued. Ordinary
Run Stop remained available. Worker PID, UID and process-generation checks,
original request receipts and the native thread remain intact; no inference is
started by the correction.

Four targeted cases passed: the original nine-level save tree through real FAT
import/export, the remaining depth/collision boundaries, old-exporter admission,
and live Goal control in an isolated coordinator plus its Stop integration.
Production build/TypeScript and strict lint passed. No provider inference or
user project execution was started for validation.

## Larger VM Exchange capacity (0.6.55)

Each VM now allows **1 GiB of payload, 4096 files and 1024 folders**, including
metadata, receipts, incomplete transfers and registered output. The six-level
Build tree and 8 MiB browser upload limit remain. The authoritative contract is
`shared/exchange-host.json`; the offline exporter, guest inventory, deployment
reservation and browser help use the same limits. A failed reservation reports
the required and allowed counts/bytes and preserves existing packages.

New Exchange disks contain a 2 GiB FAT32 partition plus the existing 1 MiB MBR
offset. On a full stopped start, an old 256 MiB partition is exported and merged
first, then rebuilt privately and replaced atomically, even without host edits.
Conflicts or copy failures preserve the existing disk. File hashing/copying uses
1 MiB chunks instead of allocating the entire file in memory. Existing volume
identity, files, history and system disks are retained. Never edit a live image
or replace a running VM's pinned worker; new deploy/run preflight checks that
worker's advertised capacity and requests Stop/Start when it is too old.

Existing hosts need this explicit, targeted maintenance once, as root:

```sh
python3 App/scripts/install-vm-exchange-support.py
```

It installs only an Exchange timeout drop-in (900 seconds), reloads systemd and
preserves running VMs, the dispatcher and their release pins. The exporter has a
600-second operation deadline; the web stop request waits for its completion.
Do not rerun the full VM/bootstrap installer. A Studio update alone does not
restart a VM or an active agent; their next admitted runs use the new workers.

Four focused checks passed: real FAT import/export and conflict preservation,
pending legacy export before resize, streaming hash of a sparse 1 GiB file, and
deployment capacity/worker guards (two backend cases and two Python cases).
Production build/TypeScript and strict lint passed. No model inference or new
project/guest test workload was started for this change.

## Agent runs without an overall time limit (0.6.54)

Normal turns and native multi-turn Goals no longer have a Studio wall-clock
deadline. The former fixed 1800-second host timer interrupted healthy work after
30 minutes, even while it was making progress. An admitted run now observes its
original native execution until completion, Pause/Stop, an actual failure or a
provider/Goal limit. No replacement timer, token budget, retry or second agent
starter is introduced. The installed worker service already has unlimited
RuntimeMaxSec and CPU time; no host reinstallation is needed.

Terminal bookkeeping also permits more than 32 commands during one long run.
Completed processes whose output has been collected release a cached handle slot;
their run-owned durable transcript retains the final exit code, signal and reason.
Polling or terminating an old completed handle returns that final status without
replaying output or executing anything. Undelivered output is retained, and four
simultaneous processes remain the concurrency limit. Individual command, RPC,
build, guest, storage and image limits keep their own scope.

Regression tests advance the actual worker's clock by seven days, checking normal
completion, native Goal continuation, the held owner lease and explicit Stop.
Namespace tests execute 65 commands as the unprivileged service user, verify old
handle readback and preserve live-process and undelivered-output bounds. This is
simulated elapsed-time qualification, not a claimed week-long production test.
The 82 focused cases, production build/TypeScript and lint passed. No additional
model inference or user project/VM execution was started for this hotfix.

## Confirmed process closure with unavailable exit status (0.6.53)

A Desktop application can end after an input such as its Quit key while the
attached guest helper can no longer obtain its exit status. A subsequent
`read_development_job` previously treated this unknown execution result as an
unconfirmed tool effect, stopping the entire agent run and pausing its Goal.

The agent adapter now distinguishes that case only when the private original
intent, start and close receipts match the project, session, execution, target,
settings and process generation, and confirm both process end and helper cleanup.
It returns `exit_status_unavailable` with the closure receipt hash. The original
job stays `unknown`, its exit code stays null, and all checks and evidence retain
their actual results. An expected exit-code criterion remains inconclusive.
Missing, damaged, foreign or incomplete receipts retain the existing protection.

Re-reading a historical unknown status-call receipt uses the same read-only
attestation. It never repeats a launch, input or other mutation, and never rewrites
the original run, tool receipt or native history. A previously stopped Goal still
requires an explicit Pause/Stop followed by Play to resume. Tool declarations,
permissions, component pins and host/data protocols remain unchanged.

Validation: seven new regressions, 77 focused tests (two skipped), production
build/TypeScript and lint. The aggregate Python discovery has existing
`skill_prompt` import collisions: its twelve affected cases also fail with the
original 0.6.52 worker and adapter, and all affected modules pass in separate
processes. The original incident's private receipts were attested read-only;
no model inference or new guest application run was used for this correction.

## Watch a VM during development (0.6.52)

The VM console opens in **Spectator mode** when a development operation holds
the VM reservation. Existing controls reconnect automatically as spectators
before the private development bridge admits guest work. Already connected
spectators remain connected. Fit/actual size, fullscreen, screenshots and
reconnect remain available; **Request control** checks admission again.
Control never returns automatically after a reservation ends.

The single-use display ticket binds the server-selected mode to the VM,
browser session and channel. A spectator's RFB connection forwards only
display negotiation and framebuffer requests. The proxy validates the private
QEMU RFB 3.8/None handshake, forces shared initialization, strips control
capabilities and rejects keyboard, pointer, clipboard, resizing, power and
unknown client messages, including fragmented/coalesced input. Manual
**View only** uses the same server enforcement. Interactive grants are checked
again at WebSocket admission, so a ticket issued before a reservation cannot
reclaim control. Existing pointer, lifecycle, settings and exchange leases,
origin/CSRF protections and two-display-per-VM/32-total limits remain in force.
No VM restart, host maintenance or data migration is required.

Focused protocol/HTTP/lease tests, build, TypeScript and lint passed. A browser
fixture with a real R4OS QEMU guest and actual development lease verified
takeover with held input, two live spectators, stale grants, control denial,
screenshots/fullscreen, reconnect/reload and 1440/320px layouts. Direct binary
input probes reached no guest input path. Only an owned guest was used;
no provider inference or user-project run was started.

## Roadmap tool contract correction (0.6.51)

New project sessions use the additive `studio-tools-v12` profile with operation-,
view-, action- and target-specific Roadmap schemas. Task and acceptance text
belongs in `description`; versions and subversions use `title`. Only text reads
accept `expectedRevision`. Validation errors identify missing/unexpected fields,
allowed fields and their context. The English contract is also composed into
future runs of existing v8–v11 conversations. All 15 previous native declarations,
thread identities, permissions and stored roadmap data remain compatible.
Existing active workers keep their bound release until the run ends.

Local host compatibility: run
`python3 scripts/agent-sessions/install-roadmap-contract-support.py` explicitly
as root before the regular update. After installing the immutable release and
waiting for admitted agent runs to finish, use its `--adopt` option. Development
and Git coordinators adopt the release at idle; adopt the Remote Host broker
with `python3 scripts/remote-hosts/install.py --adopt`, which checks active work
and closes admissions before restarting. Existing protocols and rights remain
the same. Do not reinitialize the bootstrap or replace stored session profiles.

The original Codex 0.163.0 process and an isolated local SSE fixture confirm that
the model receives the kind/field constraints (normalized update schema:
4,930 bytes, below native lossy compaction). A saved v11 conversation resumes
with the same thread and improved guidance/errors; corrected calls create one
task. Creation's conditional title/description requirement is also enforced in
the host before effects. Focused agent/roadmap/HTTP tests, build, TypeScript and
lint passed. No live provider inference or user-project run is used for testing.

## Goal Stop after delayed native events (0.6.50)

A completed worker Stop no longer hides a later native turn-start notification.
Each distinct original thread/turn receives one bounded asynchronous interrupt;
duplicate events reuse that interrupt. The RPC reader stays free to receive its
reply. Cleanup fences new interrupt tasks and waits for those already submitted
before closing the native client. Excess continued turn starts end as Unknown
and close the worker. No new turn, replacement thread or model request is started.

The original regression, two delayed turns, duplicate/foreign events, a blocked
interrupt reply and cleanup were checked. An original Codex0.163.0/actual-worker
fixture delays delivery of its real turn-start until Stop has ended, then
confirms that exact turn is interrupted. The late-event fixture uses a private
network namespace and deterministic local SSE, with no model inference. The
remote-profile regression now verifies current profile11/42 tools alongside
unchanged profile9/39 and profile10/40. All15 declaration sets are retained.

## Image pipeline qualification and retry bounds (0.6.49)

Current image-capable session profiles use the pinned OpenAI authentication,
routing, headers and capabilities with a private native provider ID and zero
HTTP/stream retries. A lost image response otherwise caused five POSTs in the
original native fixture. The bounded policy now makes one request, preserves
an unknown outcome and pauses Goal continuation. A recognized usage limit also
pauses the Goal. Existing conversations resume with their original thread ID;
Images OFF keeps the bounded provider and confirmed native image context.
Earlier tool profiles and all fifteen dynamic declaration sets are unchanged.
Running workers keep their originally pinned release.

The original Codex 0.163.0 binary and actual Studio worker were exercised with
fixed local SSE/PNG fixtures in a kernel network namespace. The cases cover
ON/OFF, account/model gates, rejected/corrupt/oversized output, storage failure,
Stop, Goal limits/lost replies, same-thread provider migration and recovery.
The project fixture executes native generation, image listing and both imports
through the actual tool dispatcher. Its original PNG hash and converted ICO/
RGBA hashes match the project sources and finished artifact resources.

Actual Zig, C and Rust consumers were built with the existing SDK0.64.92,
Contract0.64.45, Zig0.16.0 and Rust1.99.0 pins. The official inspector and bounded
payload reader confirm ICON plus named TOOLBAR/SCENE bytes in each R4X. The
256x128 raster uses multiple ABI-bounded tiles; the bitmap icon includes32x32
and64x64 entries. Rebuilding the Zig consumer without provider access produces
an identical R4X. These checks use the actual unprivileged, networkless Builder
adapter; they are not a cold-cache production service resource-budget test.

All three consumers visibly display their icon and raster in an isolated own
Full0.87.14 guest with a verified base image and private QEMU overlay. A separate
missing-resource case displays an explicit error. Per-artifact guest verification
remains a separate runner result, never an automatic consequence of compilation
or resource embedding. Browser media checks cover1440/320px, focus, reload,
protected original downloads and foreign identities. Existing project backups
include the private originals and receipts; the selected backup scope is unchanged.

No real model/provider inference was performed. Live provider image generation
remains unverified; deterministic native fixtures and actual builds/guest displays
are the qualification evidence. Own test data and guest processes are removed.

## Generated-image history and recovery (0.6.48)

Completed native image outputs have private, authenticated PNG previews and
original downloads in the transcript, with dimensions, transparency and hashes.
Expanded import cards show the actual project path and converted format. Inline
replies may use the exact `presentation.markdown` returned by the image tools.
Media references are bound to the current owner and session; opening a preview
or reloading history never requests generation or repeats an import.

Recovery reads only the original pinned-native completed receipt and original
published import journal. It checks session/thread/run/turn/item identity and
existing target hashes; unknown or user-edited targets stay preserved. A failed
image generation or usage limit pauses Goal continuation, and Stop keeps the RPC
reader available for the pause/interrupt replies. Outputs are reused from their
confirmed IDs, not attached automatically as a new user reference. Existing
image history retains its bounded image readback when generation is switched OFF.

Import resolves the unique existing spelling of `Assets`, including the SDK's
`assets` folder, and rejects ambiguous case collisions. Private capacity charges
native files, validated originals and pending conversion stages across the owner.
A full image store disables new generation without changing the saved setting.
Imported assets remain ordinary Workspace/Git sources. Private originals and
journals are outside Workspace and are included in the existing Projects backup;
Skills data remains outside the explicitly selected seven-source backup scope.
Backup uses online SQLite copies and stable files, not a global cross-file snapshot.
Confirmed project deletion removes its private image data; there is no separate
session-delete feature. No real provider inference was used for qualification.

## Agent image workflow and readonly knowledge (0.6.47)

A current English run contract explains the real native tool, confirmed Studio
IDs, conflict-protected import, original preservation, formats and explicit
RESOURCE/ICON registration plus consuming code. It keeps Generated/Imported/
Registered/Embedded/guest proof separate, requires the actual resource report
and existing pins, and explains OFF/unknown/legacy/account/write-right limits.
Inspect available references before edits; use accepted image bytes/native
output, correct reference arguments, and no assumed workspace upload. Reuse
confirmed outputs; never repair a failure through automatic generation/model
switching, new keys or invented paths. Actual human intent remains authoritative.

Small qualified companion recipes are available lazily through the existing
SDK file tools at __studio_image_recipes__/README.txt and images.zig/.h/.rs.
This readonly virtual path is explicitly a Studio companion, not an installed
SDK directory or terminal path. The private networkless reader exposes only
companion files and preserves real SDK-path collisions. No compiler/provider
process is started for a knowledge read. The index includes application-icon,
named toolbar and larger raster call patterns, buffer/alpha/stride/error notes.
Global/project prompt sources, revisions and hashes are not rewritten.

All15 native tool declarations retain their exact0.6.42 hashes; old threads
and their original schemas remain compatible. Fourteen focused instruction/
readonly-namespace/human-intent/Goal cases, Build/TypeScript and strict Lint
qualify the update without model inference. Native image bytes/protocol,
format decoders and actual R4X resource evidence remain qualified in42–46.

## Verified R4X resource payloads and consumers (0.6.46)

After the pinned official container inspector succeeds, a separate bounded
R4M0/1 reader inventories the actual finished .R4X resource payloads. It matches
kind, icon index/name, order, length and SHA-256 to the SDK-parsed declarations
and immutable source bytes; SDK HELP BOM removal is explicit. Bounds, names,
non-overlap, table size and source identity are checked. A mismatch fails the
build before publication. Resource reports bind artifact/source/manifest hashes,
project pins and the actual inspector hash. Existing artifacts are not migrated.

The report marks Embedded only after actual payload comparison. Consumer and
guest verification remain separate false fields. Builds and readonly job reads
return this bounded artifact report through existing Agent tools, with original
project/build identity checked, without adding or replacing tool declarations.

Studio companion source recipes provide a real own-module resource read,
bounded bitmap ICO/RGBA decoding and explicit alpha composition to0x00RRGGBB.
Zig uses the pinned SDK ICO decoder; C/Rust consume the converter's32-bit bitmap
ICO representation. Larger raw RGBA resources retain exact width/height/stride
and are tiled to the matched R4DRAW raster limits (currently128x128), with
caller-owned bounded buffers. This is a project representation, not an R4OS
file standard or an assumed PNG decoder. Recipe discovery follows0.6.47.

Actual isolated image-pipeline builds in0.6.45 used the existing local SDK0.64.92/Contract0.64.45 with Zig0.16.0 and the existing Rust1.99.0 profile. All three fresh R4X artifacts retain the imported icon and raster sources in their bound registration reports. User component defaults were read and preserved.

## Image resources in pinned builds (0.6.45)

The existing immutable source capture includes binary Assets files with their
actual hashes. Before compiling, Studio binds the pinned SDK catalog's parsed
ICON/HELP/RESOURCE declarations to that snapshot; it does not parse or rewrite
R4MF itself. Missing/excluded paths, links and duplicate resource names fail.
The new resourceInputs report records icon order, named resource hashes,
manifest/source identity and unregistered Assets. It reports Registered, with
embedding/consumer/guest verification explicitly false until separate checks.
The additive report is retained in build-proof.json and artifact.json.

Zig/C use the existing official manifest SDK builder and a private package
inclusion covering all captured files. Rust uses the existing pinned official
Build-RustModule script. The original project manifest, package file, compiler,
SDK/Contract and Rust pins remain unchanged. No source or build path contacts
a model or requires a full R4OS workspace.

Actual builds exposed the SDK's extra application ICON rule: a classic ICO must
include a32x32 bitmap entry. The deterministic converter now includes that entry
alongside any requested larger bitmap size (no PNG entries). Generic runtime
RESOURCE icons retain the requested size. Conversion receipts list all sizes.
This change was verified against the real SDK packer, not just an ICO viewer.

## Generated images as project assets (0.6.44)

studio.list_generated_images returns only confirmed images from this session.
studio.import_generated_image accepts a Studio image ID, an Assets/ relative
path, original/png/ico/rgba32, bounded dimensions, contain/cover and explicit
#RRGGBB[AA] background. The existing original run/workspace lease, import and
Write file permissions are required; missing folders also need Create directory.
Active terminals and unresolved project recovery block publication. Skills have
no project importer. Source originals remain unchanged.

A fixed unprivileged Pillow11.1.0 adapter has only readonly input and private
output mounts, no network, credentials or project access, plus CPU/memory/file
bounds. ICO output is actual32-bit BI_RGB bitmap data with bottom-up BGRA and
AND mask, never embedded PNG. Raw .rgba is project-specific top-down straight
RGBA, with exact dimensions/stride/hash; consuming code must match it.
Outputs and transformations are deterministic and builds use stored bytes.

Publication uses an open no-follow workspace descriptor and safe relative
parents. New targets use create-only rename; replacements require the exact
current SHA-256 and a checked atomic exchange. If a concurrent target appears,
its displaced bytes are checked and restored. Hardlinks, links, traversal and
foreign image IDs are rejected. Original tool results deduplicate retries;
private publication journals survive interruption for read-only reconciliation.
Unknown publication stops following mutations instead of replaying the import.
The tool returns asset/hash/transform data and manifest/consumer guidance;
it does not silently edit module.R4MF. Embedding and guest proof follow45–49.

Twelve targeted cases used the real isolated converter and workspace publisher,
including deterministic ICO/RGBA, alpha/aspect/crop/background, original tool
retry, source preservation, denied rights, links and a raced target replacement.
No provider/model or user VM calls were needed.

## Private native image outputs (0.6.43)

A qualified ON run activates only the original native image tool. The worker
rechecks the frozen account fingerprint before starting/resuming a thread.
Codex saves into a per-session private shadow mount at /codex/generated_images;
no project source or another provider conversation is mounted there.
The confirmed output registry uses stable Studio UUIDs and native thread/run/item
bindings. PNG bytes are decoded in the fixed networkless Pillow namespace,
with SHA-256, dimensions and actual transparency retained. Repeated items reuse
the same original. Published files survive a missing database receipt and can
be reconciled without regeneration. Corrupt, foreign or changed outputs fail.

Only image-aware workers/history reads accept up to24 MiB inbound RPC frames;
outgoing RPC remains1 MiB. Images are limited to16 MiB,16384 per axis/40M pixels,
eight per run,128/256 MiB per session and1 GiB per owner. Native history has no image-specific process file bound since0.7.27;
unknown native output is counted and retained for review.
Studio events carry safe metadata, never native Base64/savedPath/raw failures.
A native failure stops the run, including Goal continuation, without paid retry.
Stop interrupts the original native turn. list_generated_images returns confirmed
IDs; project conversion/import follows0.6.44.

Original-binary/actual-worker fixtures generated one deterministic local2.3 MiB
PNG, proved the real private save root, large frames and dynamic listing. Separate
invalid credential/foreign-output references made no image request. A delayed
local generation was stopped without an automatic repeat. These are synthetic
protocol fixtures under an isolated kernel network, with no real provider/model
inference. Existing native history is preserved. See Research evidence0.6.43.

## Native image capability and setting (0.6.42)

New project/Skill sessions use additive studio-tools-v11/studio-skill-tools-v4.
All13 earlier tool declarations retain their exact hashes and native histories.
Tools → Images defaults Image generation to ON without migrating old settings;
OFF persists through reload and name edits. A readonly account/provider/model
check uses the pinned Codex0.163.0 binary and never starts a thread or turn.
The admitted run freezes selection, engine, account policy digest and setting;
original run retries retain the original binding. Skills gain no project import.

The original binary was qualified in a network-isolated, synthetic local protocol
fixture. Image modality, provider imageGeneration, ChatGPT auth/eligible plan
and the native feature flag jointly control image_gen.imagegen disclosure.
Responses Lite carries tools in AdditionalTools input. Unknown capability remains
unknown. Public capability results contain no email, credential or raw account.

This release stages the setting and immutable tool declarations. It reports the
missing image output adapter honestly and refuses a generation-enabled worker
before launching the model;0.6.43 adds the private output path,0.6.44 the importer.
No live provider or paid image generation was used. Separate local host maintenance
extends accepted profiles while preserving the bootstrap, data and live workers.

## Goal composer and editor (0.6.26)

A two-line Goal strip sits to the left of Account/Model/Reasoning/Fast Mode.
Play/Pause/Stop use confirmed status colors and aria-pressed. Clicking the Goal
opens Edit goal with Save/Discard. Save stays paused and never submits the chat
form or its unsent text. Escape discards the draft. Empty Save clears the binding.
The dialog preserves Unicode text, uses the native4000-scalar limit, and restores
focus. Goal conflicts preserve the draft and require review of the saved Goal.

Pending, pausing, stopped, complete, blocked, limits and unavailable/unknown states
are explicit. Original request bodies/IDs survive reload in session storage; lost
answers cause reads, with only an explicit same-request retry. Model controls lock
from confirmed native active state before delayed run events. Existing run Stop
remains reachable during pending or unavailable Goal control.

Play binds both Goal and displayed session/settings revisions. A stale model choice
is rejected before a run is admitted; the selected settings are refreshed for review.
The backend requires nativeGoalExecution:2, so older active coordinators/workers keep
their release while new Play waits for compatible idle adoption. Old receipts remain
readable. Existing native threads and tool declarations are unchanged.

25 focused control/contract cases, two HTTP checks and an owned1440/320 keyboard
browser workflow qualify editing, conflict recovery, lost reply/reload, native state
labels, model-choice protection and no horizontal overflow. Send is reachable at320.
The browser uses a deterministic adapter with actual stores/HTTP; original native
runtime qualification is retained in0.6.24/25. No model inference or user VM work.
Attachment selection and paperclip follow in0.6.28–32.

## Native multi-turn Goal execution (0.6.25)

One accepted Goal run retains the same owner lease, release, provider/model/effort,
permissions, skills and project/target pins across native turns. Goal activation
and Codex idle continuation are the only starters. Original turn IDs/results are
journaled, and transcript items carry turnId. An unconfirmed turn end stays unknown.

Play is bound to the exact Goal observed at the user's request. A changed Goal or
an automatic new Goal after completion pauses this execution and requires review
and another Play. A newer native notification supersedes an older in-flight read.
Usage-only observations preserve the control revision. Native waiting-input flags
pause continuation, while unknown tool effects retain an unknown Goal phase.

The original 1800-second whole-execution limit was removed in 0.6.54. Pause/Stop/limits never
invent Goal completion or a token budget. New Play requests require the explicit
nativeGoalExecution:1 coordinator capability; older active workers remain pinned.

Five isolated tests run the actual Studio worker and original Codex0.163.0 binary
against an owned loopback SSE fixture: two native turns to complete; pause during
a turn without a next turn; native interruption with preserved text; host timeout
with paused Goal; and three turns ending blocked. No additional turn/start or
invented user message occurs; model/effort and lease are verified for every request.
Native Goal tools are present in the real request's AdditionalTools input for the
Responses Lite catalog model. Fixed local responses are protocol fixtures, with
no model inference, external network or user credentials. Additional status/actor/
read-order/goal-change checks and existing regressions are recorded separately.

## Durable session Goal controls (0.6.24)

Authenticated project and Skill-session Goal routes use additive session_goals,
goal_commands and goal_turns tables in the existing private Sessions.sqlite.
Native state is authoritative; observations, button intent and original receipts
are distinct. Revision/fingerprint conflicts cannot replace another request.
A paused controller materializes a persistent thread without turn/start, preserves
unchanged native usage, and reads back a lost reply without resending the mutation.

Play admits an owned execution with frozen settings and no invented user message.
The native Goal activates the first turn. The worker's retained multi-turn/control
foundation follows the same lease/release and has no turn/start continuation loop.
Pause permits the current turn to finish. Stop pauses before the existing run stop;
editing an active Goal pauses and fully ends that worker before applying new text.
Empty Save clears only the binding. A native stopped status is never invented.
Native continuation/recovery qualification follows0.6.25/27; composer UI follows26.

The live control channel verifies worker PID/birth and UID, and accepts only a
stored own command ID. It exposes no arbitrary RPC or paths. Unknown effects retain
the original receipts, block activation, and require explicit Pause/Stop to recover.
Coordinator restart never replays Goal commands. Lost workers remain unconfirmed.
Existing profiles and normal one-turn feature switches remain unchanged.

26 unprivileged control/regression cases and four HTTP checks pass. The actual
pinned binary/controller saves/reads/stops/clears the same owned paused thread in
an isolated namespace with zero accepted runs/inference. Fixture-controlled live
Play/Pause/Stop/edit order and two native-turn notifications are separate evidence;
this release makes no paid-model or actual native continuation qualification claim.

## Native Goal and attachment contracts (0.6.23)

The qualified Codex0.163.0 Goal RPCs and notifications are recorded in
shared/agent-input-capabilities.json with exact original source/schema/layout
fingerprints. Public owner/session/thread-bound DTOs live in agent-inputs.d.ts.
Native status and usage remain authoritative. Goal text uses4000 Unicode scalar
values after the native Unicode White_Space trim. Saving uses origin=user and
paused; unchanged text omits the objective field and never sets a token budget.

Only explicit qualified controllers may opt into features.goals. Existing
single-turn workers retain their previous switches and native tool declarations.
An active Goal set and idle continuation may start native turns without turn/start;
Studio needs one retained multi-turn run/lease, not another continuation loop.
Control/execution and UI are integrated in the following releases.

localImage is a real native input. General input_file is absent from this pinned
protocol; bounded text/PDF access needs a separate read-only attachment adapter.
Owned private image mounts avoid the1MiB RPC frame limit and contain no provider
credentials. Native model input_modalities qualify image eligibility; no model
name heuristic or separate Files/Responses client is introduced. No upload/control
is advertised before its implementation. No inference was used for qualification.

## Remote Host integrated qualification (0.6.22)

System → Remote Hosts, independent project assignment and the five bound native
agent tools are qualified as one workflow. VM development remains the default;
explicitly selected Remote Host work uses the private SSH/SFTP broker. Credentials
stay outside workspaces, native input, terminal environments and public receipts.
Original unknown effects require human review and are never silently repeated.

47 focused final integration checks cover real worker leases, v9 dispatch, bounded
SFTP packets, endpoint aliases, lifecycle review, catalog and HTTP boundaries.
Earlier retained desktop/320px and keyboard browser evidence covers editing,
project combinations, controls and lost-response recovery. Immutable compatible
broker releases are adopted only when idle; active workers keep their own release.
Installed idle adoption is recorded separately with PID/configuration preservation.

Transport/model behavior uses owned local protocol and worker fixtures. No actual
external R4OS login, paid model inference or real model target-selection claim is
made. R4OS SSH service support and native command limits are source-qualified;
network reachability and credentials must be checked for each user's chosen host.
The seven existing backup sources stay unchanged: private Data/RemoteHosts is
excluded, while project references and secret-free job journals are included.

## Shared Remote Host lifecycle (0.6.21)

Remote effects resolve the saved DNS/IP target once, record at most16 normalized
IP addresses and pin one numeric SSH peer. Shared name/IP/port locks cover all
projects and duplicate catalog aliases; a competing effect fails before dispatch.
Original unknown effects block aliases as well. Legacy uncertainty without a
recorded resolved peer requires explicit review before further effects. Bounded
VER/file reads remain possible; no lock against external R4OS clients is claimed.
SSH option parsing ends before the destination/command, and saved HostKeyAlias
trust remains independent of the pinned numeric peer.

System → Remote Hosts → Overview now lists bounded private job history and
original receipts. A human may acknowledge an unchanged unknown result after
current project agent runs end. This atomic, request-bound review records
unknown_reviewed without changing original output, exit uncertainty or remote
end proof. It permits new work and target maintenance; original request replay
still never dispatches or becomes success. Lost review replies retain the same
request ID and reconcile read-only after reload. Agents have no review tool.
An explicit offline lifecycle-cli.py supports orphaned restore receipts as the
data owner without connecting or rebinding a machine.

Broker setup now includes the existing private Projects job path, preserving
bootstrap, configuration and VM/worker units. Compatible immutable root-owned
releases are adopted only while no checks/jobs are active; admissions close
before re-exec. Existing work keeps its original adapter. The first installation
from pre-adoption releases uses explicit --adopt. New workers require lifecycle
support before remote admission. Ordinary VM work stays independent.

Data/RemoteHosts is outside the unchanged seven-source backup policy. Projects
already includes local host references and secret-free original receipts. A
restore needs conscious local target binding and uncertainty review; GitHub
Workspace metadata carries neither local Host UUIDs nor stored credentials.
Fixtures qualify alias serialization, review/recovery, immutable adoption checks,
SSH argument boundaries, HTTP and1440/320 keyboard/browser operation. No actual
Remote Host connection, user VM run or paid inference was used.

## Explicit Remote Host task guidance (0.6.20)

Bound English instructions now accompany frozen public host metadata. They
preserve normal VM build/deploy/run/test behavior, explain explicit work on the
assigned NAME, continuing that same remote task, and returning to a VM task.
Wrong/ambiguous targets, absent assignment, OFF and unavailable transport are
explained without choosing another host or blocking unrelated VM work. Passwords
stay in host settings; native R4OS commands and create-only SFTP use the bound
tools. VM tools are never redirected to a remote machine.

The prompt adds allowlisted name/description/address/port/user and historical
check data as quoted data, followed by an explicit instruction boundary. It
does not rewrite saved global prompts, Workspace/Agents.md or earlier run
snapshots. Older native profiles can see assigned public metadata but receive
no Remote binding/rights and keep New session required. Skill scope has no
project Remote instructions. No catalog process is started without assignment.

Fifteen targeted frozen-source, metadata privacy, native-call and Roadmap checks,
build/TypeScript and strict lint pass. Dialog cases qualify the written contract
and exposed capabilities; they do not claim paid-model target-routing behavior.
No real Remote Host connection or inference was performed by this qualification.

## Remote Host tools and project sessions (0.6.19)

New project sessions use additive studio-tools-v9, with get_remote_host,
run_remote_command, remote_files, read_remote_job and stop_remote_job. Their
typed schemas accept saved targets and original request IDs. Session settings →
Tools → Remote Hosts exposes the five rights, on by default for compatible new
sessions. File transfers also require the matching Workspace file permission.
Each run freezes the assigned public host metadata and endpoint/login/trust
revisions; assignment itself connects nowhere and leaves VM tools independent.

The trusted harness sends the actual inherited worker lease to the private
broker, admits once, observes the original job and streams safe host/job progress
into tool cards. Saved OFF, wrong owners/targets/revisions and missing assignment
prevent effects. User Stop cancels only this run's local remote clients even
when model Stop permission is off; unconfirmed remote endings remain explicit.
Coordinator metadata uses read-only catalog access, including in a real readonly
mount namespace. Credentials remain outside prompts, native model namespaces,
local terminals, snapshots and tool receipts.

All ten previous profile declarations remain byte-identical, including v8
Roadmap and v7 GUI schemas. Existing threads and exact permission maps are kept;
Remote tools require a new session. Skill Manager profiles have no Remote tools.
Git/development/Roadmap authorization accepts v9 with its existing meanings.
Explicit local install-remote-tool-support.py prepares the additive updater
ceiling; adopt the compatible installed idle agent and Remote Host coordinators.
Existing worker and VM units are preserved. Runtime instructions follow in0.6.20.

Validation covers native-call dispatch, real frozen runs/leases and SFTP packets
with controlled SSH boundaries, compatibility hashes, HTTP,1440/320 browser
settings/cards and user Stop. Build/TypeScript and strict lint pass. Browser
cards use isolated saved fixtures; no paid inference, real remote connection,
user-project compiler execution or VM run is claimed by this qualification.

## Bound SFTP file jobs (0.6.18)

The private Remote Host broker supports list/read/upload/download through a
bounded SFTP-v3 client on the existing pinned SSH transport. Canonical /C/,
/D/ and other real drive paths preserve UTF-8 names and spaces. Limits are
1023 UTF-8 path bytes,255 UTF-16 units per component,128 returned directory
entries,16 KiB tool reads,8 MiB transfers and120 seconds. No VM exchange drive,
guest helper, FTP, overwrite, rename or delete fallback is assumed.

Uploads snapshot a hash-bound readable Workspace file or an explicitly selected
verified current-project artifact from the current session or a user build.
The native server must accept create-only OPEN and CLOSE publication; every
byte is then read back and hashed. Original receipts retain acknowledged staged
bytes and CLOSE separately from complete readback. Losing a write/CLOSE reply
preserves unknown state and never sends the upload again.

Downloads require the run's Workspace write permission and a selected remote
SHA-256. They create new files with descriptor-relative, no-follow, create-only
atomic publication. Existing files and editor drafts are kept; replacement is
explicitly unavailable and requires choosing another local path. Case clashes,
links, private paths, changed source hashes and appeared destinations are refused.
Snapshots stay private and are removed at terminal handling; their original
hash and target remain in the job receipt. Native declarations follow in0.6.19.

Validation: six worker/SFTP-packet tests with an actual local protocol fixture,
six command/lease regressions, three HTTP checks, build/TypeScript and strict
lint. Controlled artifact metadata tests do not claim an app build. No real
SSH/R4OS host connection, VM run or paid inference was performed.

## Durable Remote Host command foundation (0.6.17)

The unprivileged broker now records project/session/run, the frozen host and
endpoint/login/trust revisions, exact request arguments and deadline before a
possible SSH command. Its separate private agent socket requires the actual
worker parent and inherited workspace lease. Repeating an original request
reads its receipt; another session cannot read or stop it. The bounded harness
waits on that original job and never retries command dispatch after a lost reply.

Commands use native R4OS SSH Exec, with one command and no assumed POSIX shell,
persistent working directory or remote compiler. Confirmed command exit status,
SSH transport uncertainty and local client termination are separate fields.
Timeout, output overflow, Stop and broker interruption preserve an unknown
remote effect rather than inventing a command exit or confirmed remote end.
Unknown effects block later mutations at the same configured endpoint; explicit
VER diagnosis remains available. DNS alias qualification follows in0.6.21.

The reserved studio-tools-v9 broker contract is exercised by controlled worker
fixtures. Native declarations, session rights and live agent admission follow
in0.6.19; installed commands remain unavailable until that compatible profile
is enabled. The explicit local install-job-support.py only adds the existing
Projects directory to this private broker's writable namespace. It grants no
web terminal, general shell or VM administration rights.

Validation: six real worker/SCM_RIGHTS/receipt tests, fourteen transport/catalog
tests (including actual local subprocess output, timeout and cancellation),
three HTTP tests, build/TypeScript and strict lint. SSH response fixtures do
not qualify a real R4OS handshake; no remote host, user project, VM or paid
inference was used. Detailed receipts remain in the local Research directory.

## Independent project Remote Host assignment (0.6.16)

New Project and GitHub import completion offer Remote host / None alongside an
independent Virtual machine choice. Projects → Settings → Remote host provides
Save/Cancel, dirty guards and revision conflicts with retained drafts. Safe current
names/endpoints and missing-catalog states are shown; a host may be assigned even
without a successful prior check. Assignment never connects, installs/deploys,
changes the normal VM target, edits sources or replaces SDK/compiler pins.

An optional project_remote_hosts table in the existing Projects.sqlite stores
UUID references with ON DELETE CASCADE. It is created only on an explicit non-null
assignment; legacy reads return remoteHostId:null without changing database bytes
or creating rows/schema. Assignment and project revision commit atomically. A
shared read-only descriptor on the global catalog lock prevents racing central
deletion without granting the development host extra write rights. Names remain
central metadata; renaming keeps UUID references. Global removal is blocked while
any ready/pending project refers to the host. Multiple projects may share it.

Creation/import validate the same local UUID and keep their original request and
source/pin journals. Imports take VM/Remote choices explicitly from the local
completion, never repository metadata; portable project.json omits both local
UUIDs and all credentials. Missing legacy request fields keep their original
fingerprints. Session removal has no global host ownership; confirmed project
deletion cascades only its local reference. It never connects to or removes remote
files/hosts. Active or unknown private remote jobs block reassignment and deletion.
The fixed store CLI now shares its typed ProjectFault with imported helpers so
these conflicts retain their correct HTTP status.

Seven project/publication/delete tests (including an actual read-only bwrap mount),
a real Git import/publication test with controlled SDK validation, two HTTP tests,
browser1440/320, build/TypeScript and strict lint qualify this scope. Actual browser
settings use the real API; New Project options and its captured POST are controlled
UI contract fixtures. Core creation publishes real files using a controlled trusted
template/SDK fixture. No real compiler, VM, repository/account or remote connection
is used, and own temporary test data is removed. Existing data/pins/VM PIDs remain.

## Remote SSH target and explicit checks (0.6.15)

The private unprivileged broker uses the existing pinned SSH/SFTP binary hashes
and native R4OS VER parser, with a separate saved endpoint/login/trust adapter.
It uses no VM lease, NAT forward, image/boot identity or hardcoded VM login.
Only an explicit Check connection admits VER; save/open/reload and capability
reads never connect. Native zero exit, R4OS release and active kernel are all
required before confirming R4OS. Offline, authentication failure, changed key,
not-R4OS, timeout and transport failure remain distinct historical outcomes.

Private runtime askpass files (0700/0600) supply passwords without argv/env secrets.
Fixed arguments exclude external SSH config, proxies, forwarding, agent/identity
keys and local commands. A first explicitly observed key is TOFU, including on
failed login; this is not independent identity proof or confirmed R4OS. Existing
trust is strict. Changed keys are never automatically accepted. An explicit,
revisioned Reset host trust preserves check history and only allows a later
explicit check to bind a new key. Endpoint/login changes invalidate readiness;
active checks block target/login/trust/delete changes, while renaming stays safe.

A secret-free intent precedes the connection. Original check IDs/results survive
lost HTTP replies, interruption and broker restart without automatic connection
replay. Trust and last-test metadata share an atomic SQLite request receipt;
that receipt reconciles a lost sidecar-file write. Stale target revisions cannot
publish readiness. Checks are limited to4, private clients to16, frames to16KiB,
output to64KiB per stream and the check deadline to15s. History is limited to1000
checks; interrupted temporary journal writes are retained and bounded.

The explicit local `scripts/remote-hosts/install.py` prepares only a root-owned
launcher/configuration and r4os-studio-remote.service. After the normal immutable
update, `--adopt` starts it as r4os-studio with a private Unix socket, constrained
write paths and network families. Runtime ownership is exclusive; an idle broker
closes admissions before adoption, and active checks prevent its restart. No VM,
agent/build worker or bootstrap configuration is replaced. The broader command/
file-job lifecycle and automatic release adoption are qualified later in0.6.21.

Eleven targeted Python tests exercise the actual pinned client's offline -G
configuration and executable private askpass, plus controlled SSH outcomes,
trust, target changes, atomic lost-result recovery, restart and adoption. Two
HTTP tests use the real catalog and private Unix broker with a controlled SSH
boundary. Browser1440/320 proves explicit tests, fingerprints/version display,
key conflict/reset, login failure and lost-POST reconciliation without repeat.
These fixtures are not a real remote R4OS/SSH handshake; no actual external host,
VM, model or paid inference was used. Root-installed read-only capability/UID
checks separately verify deployment without connecting to a saved host.

## Remote Host browser management (0.6.14)

System areas now follow Settings, Virtual Machines, Remote Hosts, Updates.
Remote Hosts has + New Host and UUID-bound names in the second column, with
Overview/Settings in the third. Deep links use #system/remote-hosts/UUID/settings
or /overview; reload and browser back/forward restore the actual host/view.
Existing #updates links select Updates after the navigation addition.

New Host offers editable name/description/address, port22, user r4os and a masked
rosebud default. Existing hosts display no password input until an explicit
Change password selection; saving or cancelling clears entered secret text.
Ordinary edits preserve the stored password and UUID. The overview shows current
safe metadata, actual saved test status and fingerprint. Check connection stays
unavailable until the SSH adapter is installed; viewing/saving does not connect.

Save/Cancel, dirty-navigation and unload guards, preserved stale drafts with
explicit reload, confirmed local removal and bounded retry of an original
uncertain request are integrated. Secrets are not persisted in browser storage.
List/detail generations and aborts prevent delayed other-host replies from
binding the selected form. Host names are data; a host named LLM Provider cannot
select provider features. Empty/unavailable/missing-host states offer retry.

Isolated real-API browser evidence covers default/custom logins, password-free
stored views, save/cancel/conflicts, keyboard focus,1440/320 layouts, deep-link
reload/back/forward, delayed detail responses and confirmed local removal.
Build/TypeScript and strict lint pass. The shared hook continues the ordinary
initial provider-metadata read; no provider account action or SSH test is invoked.

## Private Remote Host catalog (0.6.13)

`/api/remote-hosts` provides local create/list/read/revisioned edit/confirmed remove
under an independent HttpOnly browser session, host/origin validation and CSRF.
A saved UUID has an NFC/case-insensitively unique name, optional description,
validated DNS/IPv4/IPv6 endpoint and SSH port (22 by default). New entries use
user r4os/password rosebud; explicit own values are preserved. Public projections
contain passwordConfigured, never a stored password. Editing without password
preserves it; endpoint/credential changes increment their separate revisions,
invalidate previous readiness and clear trust only for a changed endpoint.

The private SQLite catalog is `Data/RemoteHosts/RemoteHosts.sqlite` beside the
existing provider store, with schema/application binding, separate secret/key
rows, stable UUIDs, monotonic revisions and original request fingerprints/public
receipts in the same transaction. Exact retries return the original result;
changed request reuse, stale revisions and duplicate names conflict. File modes
are 0700/0600, links/foreign owners/hardlinks and invalid schemas are refused,
and corrupt bytes are preserved. Bounded local flock and SQLite transactions
serialize metadata changes. No catalog operation contacts or changes a host.

The fixed broker protocol and typed frontend API are prepared; browser management,
SSH testing, project assignment and agent execution arrive in later subversions.
No SSH or arbitrary local command route is available here. Run the explicit local
`scripts/install-remote-host-support.py` once for the existing deployment: it
prepares only the private owned folder and one service ReadWritePaths drop-in;
the next normal Studio update adopts it. Bootstrap/updater hashes and VM services
are preserved. RemoteHosts is outside the unchanged seven backup sources.

A real isolated HTTP/SQLite test covers default/own credentials, password-preserving
edits, public secrecy, exact replay, conflict, DNS/IP/port validation, independent
session guards, restart, confirmed local deletion and corrupt-catalog retention.
A filesystem test verifies linked ancestors/directories/databases and hardlinks
cannot modify foreign files. No actual login or network connection was used.

## Integrated project-roadmap acceptance (0.6.12)

The internal project-roadmap scope (0.6.1–0.6.12) is implemented. Isolated
acceptance uses two projects with three/two saved sessions, including two v8
sessions each and a retained v7 native thread. Bound tools and an actual browser
save share the same notes; another browser's stale save keeps its draft/focus
and reports a conflict. Distinct open/done/discarded child states and every note
level survive a complete original archive and the single atomic 0.1.X → 0.2.X
rollover. The next version has empty vision/notes/subversions. Actual limited
file tools write/read back durable knowledge under Docs before completion.

Browser evidence covers default ON, explicit OFF, Save/Cancel, old-profile hints,
keyboard controls, desktop/320px, streamed archive hash, retained local input,
version-scoped paged history/tool receipts, reload and an actual isolated backend
restart using unchanged stored data. The second project's Roadmap bytes and old
native thread/profile remain unchanged. Original native histories are preserved.
Network event notifications are a controlled SSE fixture; no model is invoked.

Targeted qualification: 28 storage/domain/cleanup tests, 16 active-run broker/
prompt/lifecycle/backup tests and the protected HTTP API test, plus build,
TypeScript and strict lint. Conflict, open-work, missing rights and lost-response
recovery cases exercise the real journal/broker. SDK file context alone is an
empty isolated fixture; no compiler, VM or paid inference is required. All own
QA directories/test servers are removed after checks. Internal cleanup requires
an actual explicit user cleanup request; normal roadmap implementation does not
archive or complete the external main roadmap.

## Roadmap lifecycle and isolated restore (0.6.11)

Roadmap identity belongs to the immutable project UUID. Renaming a project or
removing an unused session does not change its common Roadmap database. Existing
project lifetime/workspace locks prevent deletion while a reader or worker is
active. Confirmed project deletion removes only that project's Roadmap, export
cache, workflow journal, sessions and Workspace docs; interior links are unlinked
without following them. Other projects, global settings and VMs remain intact.

The existing seven-source backup already covers every Roadmap.sqlite using its
SQLite online backup, including committed live-WAL rows; it omits database
sidecars after the snapshot. Private workflows/export receipts, original session
evidence and Workspace/Docs are in the existing Projects source. No backup source,
timer, VM inclusion or host permission was added. Each database is consistent;
its snapshot and separately copied documents are not one global transaction.

After restoring only into a new isolated offline directory, use the matching
release's manual read-only diagnostic:

```sh
python3 scripts/project-roadmaps/inspect_restore.py --offline \
  --projects /absolute/new-restore/App/Data/Projects --project PROJECT_UUID
```

It validates registered project/schema bindings and compares archive/document
hashes, original stored cleanup intent and workspace identity with workflow
receipts. It does not activate data, acquire/create runtime locks, rewrite files,
rebind an inode, finalize a workflow or create a next version. A restored workspace
has a new inode; pending workflows require reconciliation even when all bytes
match. Keep original snapshots, receipts and file order together, inspect any
cross-file drift and review durable Docs. After deliberate activation by existing
host maintenance, cancel an old pending workflow and prepare again only against
the reviewed restored state and original valid cleanup intent. Cancelling retains
the archive and documents. Missing intent or conflicting archives require review;
neither a new authorization nor a successful rollover is fabricated.

Only deliberately selected Workspace docs participate in Git status/commits and
normal ignore rules. Private Roadmap, settings and Sessions are siblings outside
Git/agent file namespaces. Imports preserve source docs and exact portable pins,
receive a new project UUID, and initialize their own empty internal roadmap only
on explicit initialization. An old text changelog is not imported as live state;
there is no automatic external R4Roadmap import. SDK/manifest validation remains
the existing pinned adapter; the isolated registration test uses a controlled SDK
fixture and does not claim a compiler run.

Qualified native v8 and legacy profile gates remain additive and unchanged; this
release needs no new host installer or root/bootstrap change. Two isolated actual
broker/lifecycle/backup tests and a source-only real-Git import/registration test
cover the behavior above, without accounts, inference, user projects or VMs.

## Roadmap cleanup finalization and history (0.6.10)

`cleanup finalize` now rechecks the actual original user-message hash/context,
active frozen Roadmap permission, Read file permission, exact workflow/version/
revision, complete original archive and the verified document selection, summary
and final byte hashes. It reads the existing files without creating directories
or rewriting archive/docs. Its one SQLite transaction marks the old main version
Complete, inserts exactly one next empty version, switches current, and stores
workflow and request receipts. For example 0.9.X becomes 0.10.X; the new version
is New/Open with empty vision, notes and subversions. Project notes, other
versions, historical entries and all child statuses/notes remain intact.

An existing next number, unresolved work, changed files, changed original user
context, missing checkpoint or stale binding is a conflict. Numeric overflow
also preserves the original state. A pre-commit failure rolls all three database
changes back; a lost post-commit response is reconciled through the original
workflow/request. Repeating even a new finalization request for the same completed
workflow returns its recorded next version rather than creating another one.
An old consumed cleanup request cannot roll over the new empty version again.
The archive remains the immutable snapshot of the prepared state; the completion
receipt records the subsequent atomic database transition.

Pending user intent is read from actual stored session messages without an
arbitrary twenty-message cutoff. Its cursor is closed before long archive work,
and finalization can recheck an original request from another session of the
same project. Native profile declarations, threads, histories, custom prompts
and project pins remain unchanged. The bound English capability guidance reports
that finalization is now available; no second blanket approval is introduced.

The roadmap overview and version views display Cleanup history with original
workflow ID, snapshot revision, phase, archive path/hash/download, verified
knowledge receipts and next version. Protected read-only workflow routes use
project/version-bound keyset pagination and omit private journal internals.
Recent entries update periodically; loading older history leaves it stable until
Refresh. Workflow updates retain form drafts and focus. Tool cards also show
workflow ID and cleanup phase. All file mutations still use the bound agent
workflow; browser history reads cannot finalize or cancel a workflow.

## Roadmap cleanup preparation (0.6.9)

The bound v8 cleanup tool now enables `prepare`, read-only `status`, and `cancel`.
Finalization remains unavailable until 0.6.10. No main-version status or current
binding changes, and no next version is created by preparation or documentation
confirmation. Native declarations remain exactly those from 0.6.7.

An initial prepare needs `cleanupRequested:true`, a stable UUID request ID and
the exact current version/revision. It links the caller's explicit intent to a
real user cleanup request in this project's session, including a pending request
from an earlier run. A consumed active/completed request cannot start another
workflow; reconciling a cancelled attempt for the same version can retain the
original authorization without another blanket confirmation.
The host also requires frozen Read file, Write file and Create directory rights,
the original run/worker/lease and no live terminal processes. It serializes with
this run's file/terminal tools and never reacquires an independent workspace lock.
Open subversions/tasks/checks must be resolved honestly; discarded work retains
reason notes and historical child statuses. Nothing is silently marked done.

The private SQLite workflow journal retains version/revision, workspace identity,
original user request hash, baseline document hashes, archive attempts and exact
request receipts. A complete immutable 0.6.5 export is copied and hash-verified
at `Docs/Changelogs/0.1.X.txt`. Descriptor-relative no-follow directory/file access
and atomic no-replace publication preserve other targets. An identical original
archive is confirmed; a different archive or a link is a conflict. Interrupted
own stages are retained and a subsequent original prepare can resume without
rewriting a published archive. Active workflows block ordinary roadmap edits.

The agent reads existing Docs files and makes meaningful knowledge updates with
the separately permitted file tools. A second `prepare` uses a **new** request
ID, original workflow/version/revision/current binding, `cleanupRequested:true`,
`documents:[{path,expectedSha256,sha256}]` and `documentationSummary`. The server
checks original baseline hashes, canonical regular UTF-8 files under Docs outside
Changelogs, actual final hashes and the complete original archive again. It never
rewrites documentation or claims to verify the semantic completeness of the
agent's selection. Empty selections require an honest summary. Confirming a
missing archive fails without recreating it.

`status(workflowId)` returns the original archive/document receipts and phase;
these are historical verification receipts, not a continuous claim about current
file contents. Optional `documents` selects at most eight receipt paths with their
known current hash and `expectedSha256:null` to recover original/recorded hashes
without file writes. Exact request replay returns its original result. `cancel`
releases the workflow while preserving archive, stages and document changes.

Limits: 512 baseline documents, 4 MiB per knowledge file and 64 MiB total baseline,
12 directory levels, 1,024 entries per directory, 32 confirmed documents, eight
archive attempts, 192 MiB staging, the existing 96 MiB complete-export limit,
1,000 workflows and existing 64 MiB database/50,000 receipt limits. Exhaustion,
conflicts and interrupted phases preserve data for reconciliation. No automatic
root installation, external API, project/VM reset or paid model inference is used.

## Bound Roadmap instructions (0.6.8)

Every new qualified project run receives the release-bound English contract in
`shared/project-roadmap-instructions.txt`, appended to its frozen global/project
sources. Both the default prompt and saved custom prompts use this composition;
saved text, revisions, hashes and `Workspace/Agents.md` remain exact. OFF and old
native profiles receive an explicit availability notice; Skill Manager sessions
receive no project Roadmap contract. Existing worker releases stay pinned.

The contract separates normal roadmap implementation from an explicit cleanup
request. It requires read-before-write/current revision, preserving notes and
history, separate tasks/checks and actual evidence. Cleanup triggers, complete
UTF-8 archive, durable Docs knowledge, readback/hash verification and exactly
one next empty version are explained in order, with no extra blanket approval.
Unknown receipts, unavailable phases, open work, archive conflicts, file rights
and concurrency must be reconciled; no status-only or shell bypass is authorized.
The native v8 declaration/schema is unchanged by this prompt integration.

## Bound project Roadmap tools (0.6.7)

New project sessions use additive `studio-tools-v8` with
`studio.read_roadmap`, `studio.update_roadmap` and `studio.cleanup_roadmap`.
The original v1–v7 and Skill declarations remain byte-identical; their native
threads and histories keep their profiles. One `roadmapEnabled` switch controls
all three tools, outside the original individual permission map. Old sessions
show **New session required**; ON alone does not make tools available.

The host checks frozen project ownership and the switch on every call, including
historical result replay. A fixed unprivileged Python sidecar rechecks the
actual worker PID/birth/release, session/run/revision, original durable tool
intent and inherited workspace lease descriptor. Short mutations are serialized
with Stop admission. It uses the same project lifetime lock, private database,
strict read/mutation functions and durable UUID request receipts as the WebApp;
it never requests a second unowned workspace admission. No project ID, SQL,
service URL or host path is accepted from the model. Roadmap files are outside
the workspace mounted into terminal/build/native namespaces.

Reads return bounded metadata/text previews with explicit byte lengths and
hashes. Use `view=text` to read every UTF-8-safe byte page of notes, description
or vision; collections have revision-bound cursors. A prepared immutable export
can also be read in byte pages and verified by its complete SHA-256. Stable
request IDs and `view=receipt` reconcile lost responses without repeating effects.
Tool cards retain bounded arguments, result revision/current version/request ID,
conflicts and unknown outcomes.

The full cleanup prepare/status/finalize/cancel input contract is declared now;
these phases explicitly return unavailable until 0.6.9/0.6.10. No cleanup is
emulated with ordinary edits. English tool descriptions already explain the
explicit cleanup triggers and complete archive → Docs knowledge → verification
→ Complete → exactly one next empty version sequence. Run prompt integration
follows in 0.6.8.

Explicit host compatibility maintenance before installing the v8 release:
`python3 scripts/agent-sessions/install-roadmap-tool-support.py`. It verifies the
existing updater hash, keeps a backup, preserves its configuration and changes
only the accepted additive profile ceiling. After regular installation, use
its `--adopt` mode only while agent workers/admissions are idle. Existing workers,
VMs, providers, histories, pins and user data are retained. Git and development
host authorization include v8 with the same existing frozen rights.

## Roadmap session preference (0.6.6)

Project Session settings → Tools → Roadmap has one default-on switch.
Missing `roadmapEnabled` is read as true without rewriting saved sessions;
explicit false is retained. Save/Cancel, dirty guards, session revisions and
busy-run restrictions use the existing settings flow. Each accepted run freezes
its own choice; earlier accepted runs and native conversation content remain.
Skill Manager sessions have no project Roadmap setting or access.

The preference and actual tool availability are shown separately. The qualified
original Codex 0.163.0 schemas expose `dynamicTools` on `thread/start`, without
a corresponding field on `thread/resume`. Old v1–v7 and Skill profiles, native
thread IDs, histories and permission keys are preserved. `studio-tools-v8` is
reserved for the additive declarations in 0.6.7; creating a session in 0.6.6
still uses v7. The UI states that a new session after that update is required.
See the [official App Server documentation](https://learn.chatgpt.com/docs/app-server)
and the locally qualified original schemas for this compatibility decision.

The coordinator advertises `roadmapSettings:1`; a new project run requires that
capability and a compatible worker release before admission. Older accepted
worker releases continue normally. The Roadmap host gate requires a matching
project owner, frozen ON and the additive profile before any Roadmap operation.
No Roadmap tools are activated by this settings-only release.

# R4OS Studio · App

## Version history and complete UTF-8 roadmap exports (0.6.5)

Main versions retain their full hierarchy after status/current-selection
changes. A selected current or historical version can be exported as
`0.1.X.txt`, without a V prefix. Export saved version prepares an immutable
server snapshot and downloads its verified UTF-8 text. Project roadmap notes,
description, version vision/notes, every subversion, task and acceptance item,
all notes, discarded work, stable IDs, ordering, statuses, revisions and
timestamps are included. Internal receipts are not roadmap entries.

The fixed adapter uses a verified SQLite backup, streams a deterministic
archive, seals length/SHA-256 and publishes atomically under private
`Roadmap/Exports/<request-uuid>/`. Only the selected version's text and metadata
are retained; the temporary database copy is removed. Repeated request IDs
return the original result even after subsequent roadmap edits. Preparing or
downloading an export changes no roadmap revision, content, status or current
version and creates no next version. No Workspace changelog is written by a
download; explicit cleanup remains a later, separately invoked workflow.

POST exports uses Projects session/host/origin/CSRF and frozen version/current/
revision binding. Downloads require the same project session, verify SHA-256
before streaming, preserve UTF-8 bytes and have bounded backpressure, concurrent
streams and lifetime locks. The internal adapter also supplies bounded UTF-8
chunks with safe continuation offsets, revision and hash. Cache bounds are
96 MiB per complete archive, 512 MiB including staging and1024 entries per
project, with preparation deadlines. An invalid, corrupt or oversized export
fails while preserving source data; a partial file is never published as a
complete archive. Existing export files are not overwritten or silently pruned.
Roadmaps require the current Workspace layout so private storage stays outside
all source namespaces. Legacy projects must migrate sources first. If an old
legacy project already has private roadmap data, the source migration refuses
to move that data into Workspace and preserves all files for explicit recovery.

## Roadmap subversions, tasks and acceptance items (0.6.4)

Selected main versions now show expandable subversions with their own number,
title, status, description, notes and separate progress. Add/edit and explicit
up/down ordering use the shared revision-bound API. Ordering requires the full
loaded collection. Expansion is remembered per project/subversion in browser
session storage.

Tasks and acceptance items are separate collections, each grouped into Open,
Done and Discarded. They support create/edit, explicit status changes, readable
notes, append/replace notes and confirmed targeted deletion. Deleting a
subversion names its child counts and removes only that hierarchy. Completing
tasks does not complete acceptance items or change a version's status.

Dialogs share the existing Save/Cancel, focus, dirty/conflict and original-request
recovery behavior. Parent/version IDs and current revision remain frozen for
each submitted change. Other edits must be saved or cancelled first; errors do
not discard drafts. Notes render as text, pagination and outputs stay bounded,
and delayed responses cannot replace another project's selected view.
While visible, a small revision read every five seconds reports changes from
another view without replacing open input. Refresh remains an explicit action.

## Project roadmap navigation and main versions (0.6.3)

Projects now includes Roadmap between GitHub and Settings. Its third column
shows Overview, + New Version and the project's versions with status and a
Current marker. Initializing a missing roadmap is an explicit button action;
opening a view does not create data. Overview edits project roadmap description
and notes. A selected main version shows number, title, status, vision, notes
and separate task/acceptance progress. New versions start without inherited
notes, vision or children. Make current version is a separate explicit action.

Project/version hash links, reload and browser history preserve the selected
view without changing the shared current version. Save/Cancel and navigation
guards retain draft input on conflicts. Unconfirmed saves retain their original
request in session storage and offer Retry original request; retries do not
create a second version. Responses are aborted or ignored after switching
project/view, and inconsistent revisions require refresh. Subversion/item
editing and native roadmap tools remain subsequent work.

## Internal project roadmap API (0.6.2)

Project-session-protected routes under `/api/projects/:id/roadmap` expose
overview, current/historical versions, subversions, tasks and separate
acceptance items, including notes on every level. Reads never initialize a
missing roadmap. Explicit `POST /initialize` uses a durable request ID.
`POST /mutations` accepts narrowly typed create/update/status, append/replace
notes, complete-collection reorder, confirmed removal and explicit current
version selection; replacing an entire roadmap is not an editing operation.

Each accepted mutation binds the project, exact target/parents, expected
roadmap revision, current main version ID and unique request ID. The original
result is stored in the same SQLite transaction; exact retries return that
result even after later edits, while changed input, stale revisions and old
current bindings return conflicts. Concurrent note appends use short
transactions and retain the rejected input for a reconciled retry. Browser
session, allowed host/origin and CSRF checks use the existing Projects policy.
Private database paths are never accepted from clients or returned in errors.

Collection pages hold at most20 entries and continuation cursors bind project,
parent and revision. Edits invalidate older cursors. Notes/text, request and
response sizes, entry counts, stored receipts and database size are bounded.
Versions and work items keep distinct status models; completing tasks does not
implicitly complete or roll over any version. Browser editing and native agent
tools remain subsequent work. No existing project is initialized on installation.

## Shared project roadmap storage (0.6.1)

Project roadmaps now have a typed hierarchy and a private, project-scoped
SQLite store at `Projects/<project-uuid>/Roadmap/Roadmap.sqlite`, outside
Workspace and Sessions. The fixed unprivileged `scripts/project-roadmaps/cli.py`
adapter supports read and explicit initialize. Merely starting or updating
Studio does not initialize existing projects. First explicit initialization
atomically creates one roadmap with an empty `0.1.X` / New / Open version;
subsequent calls and separate processes use the same IDs and content.

Versions, subversions, tasks and separate acceptance items retain their own
notes, status, ordering, revisions and timestamps. Parent constraints and
different version/item status models are enforced in SQLite. Existing corrupt,
unknown or foreign-project databases are preserved and fail visibly; they are
never treated as missing storage. Project lifetime locks coordinate deletion
without taking the workspace lock or blocking ordinary agent work.

This release provides the storage and backend adapter foundation. Browser
routes/editing and agent tools follow in subsequent roadmap versions. No
project database is mounted into agent, terminal or build namespaces. Existing
Projects write paths already cover the new storage; no host installer or
automatic migration is required.

## Compiler timing guidance (0.5.17)

The shipped English System Prompt recommends `timeout_ms=120000` for ordinary
compiler work and up to `600000` for cold caches/larger SDK compilation.
`yield_time_ms=1000` only returns output early; it does not shorten the process
lifetime. Continue with the same process handle, or use the separately permitted
project build tool's internal job wait. One-second compiler budgets are avoided.
These are instructions within the unchanged terminal limits, not longer host
deadlines or permission to run unrequested builds/tests.

The same additive timing guidance is composed for terminal-enabled project and
skill runs using saved custom prompts. Matching default text is not duplicated.
Saved prompt text, revision and checksum are retained; existing/admitted workers
keep their release and frozen sources. No prompt reset, session migration or
native thread replacement is needed. Build/TypeScript, strict lint and static
Python/prompt-contract review only; no tests or compiler/agent/project/VM probes.

## Extended owned-window input (0.5.16)

New project sessions use additive `studio-tools-v7` with the same 31 permission
names and defaults. `studio.send_vm_input` accepts `guiText`, printable ASCII
keys, arrows, Backspace/Delete, Home/End, PageUp/PageDown and Shift+Tab. Key-only
`repeat` is bounded to 1–16 queued codepoint events, not a physical held key.
GUI text is bounded to 64 Unicode characters/256 UTF-8 bytes without C0/C1
controls; send Enter separately. App event consumption must still be observed.

All GUI input uses a recent image, the owned process generation and the focused
window's observed geometry. New deployments advertise/confirm `guiInputVersion:2`
and `guiFrameBindingVersion:1`; older helpers reject extended input before any
effect and require deploying the existing artifact again. The helper bounds
enqueue time, rechecks the window during batches and reports partial acceptance.
No global QMP, physical key hold, clipboard paste or additional permission is
introduced. Console `text` stays separate. Existing profiles can send GUI text
using their already-declared `kind:text` plus `frameId`; their original key enum
is retained and full navigation requires a new session. Histories are not reset.

The installed Codex 0.163.0 experimental schema declares dynamic tools only on
thread/start, not thread/resume; v1–v6 declarations remain unchanged. Development,
update, GitHub and frontend profile gates all include v7. Explicit local
`python3 App/scripts/agent-sessions/install-gui-input-support.py` qualifies the
existing root updater hash and adds v7 without removing old rollback contracts.
After regular installation, `--adopt` adopts the agent coordinator only if all
workers and admitted runs are idle. Never download/run a privileged installer.

Build/TypeScript, strict lint, Python/Zig AST and static original SDK/native-schema
review only; no tests, helper/app builds or agent/project/VM input runs performed.
Actual guest input validation remains unperformed under the requested scope.

## Confirmed Stop command receipts (0.5.15)

Stop command success is separate from the development job's outcome. The
coordinator returns a bounded receipt for a confirmed worker end or the exact
owned process closure/cleanup proof. An intentionally stopped job remains
`interrupted`; its Stop tool card can be `completed`. Already ended and never
launched applications are distinguished. Unknown/missing cleanup evidence stays
unconfirmed and is not retried. Other guest jobs only confirm their host worker
ended; completed guest writes are retained. No timeout or failed check becomes
a passed job, and historical tool receipts remain original.

New agents require `stopReceipts:1` before sending Stop. Coordinators and workers
retain normal idle adoption/release binding. Job state alone or `busy:false` is
insufficient proof for an application Stop. The browser shows the command
receipt separately from the actual job result. Build/TypeScript, strict lint and
static Python review only; no tests or new Stop/agent/project/VM runs performed.

## Animated Desktop screenshots (0.5.14)

Capture distinguishes changing content from process/window identity. It checks
the same live process generation, native window, geometry, visibility and focus
before and after the bounded QMP capture; ordinary `guiRevision` changes are
recorded rather than rejected. Immutable evidence includes `windowObservation`
and `captureObservation` with timestamps and both content revisions. This is an
observed interval, not an atomic guest-frame guarantee. Real identity/geometry/
focus changes still reject the capture. No global VM pause is used.

Input accepts a matching window image for 30 seconds; visual check completion
uses 120 seconds. Later animation frames do not invalidate the observation.
Historical evidence retains its original content-equality rule. New helpers
advertise `guiFrameBindingVersion:1` and verify the expected window/geometry
again in the guest before input; old helpers retain their content-revision guard
and require a new deployment for animation input. Guest helper pins remain
independent of project pins. Existing deployments and native histories are not
rewritten. Input acceptance never proves application consumption.

Build/TypeScript, strict lint and static Python/Zig syntax/source review only;
no test suites, agent/project/VM runs or actual animated guest capture were run.

## Native Web search session tool (0.5.13)

Session settings → Tools → Web → Web search is ON by default in project and skill
sessions. It uses the existing Codex provider to search, open pages and find text;
availability remains subject to the selected model/account. The additive
`webSearchEnabled` setting defaults to true when absent and is frozen at run
admission. OFF is explicit; settings require the same revision and idle guards.
Existing native threads and v1–v6 dynamic declarations are retained, with no
session migration. Previously accepted runs keep their original release/snapshot.

Codex 0.163.0 receives `web_search=live` or `disabled` both at process preparation
and thread start/resume. The existing forced `supports_search_tool=false` stays:
it controls general tool discovery, not hosted web search. Other native features,
terminal/build network isolation and provider credential handling are unchanged.
New runs require the coordinator's nativeWebSearch capability and a compatible
worker; old snapshots without this field remain OFF. No separate search API key
or downloaded privileged installer is needed. Idle coordinators adopt normally.

Native `webSearch` lifecycle events are stored as tool cards with bounded Search,
Open page and Find in page metadata. Only approved query/action fields and up to
24 unique HTTP(S) result links are projected; opaque result bodies stay in the
native conversation. No URL is fetched by Studio's browser or Python adapter.
Ordinary Markdown source links can be displayed in answers. Local file Search
remains separate. Interrupted/unfinished cards use the existing run recovery;
unknown effects are not replayed. Turning search off does not erase previously
retrieved material from the preserved conversation.

Qualified against official configuration/app-server documentation, original
source 8c076942cb70fba8e5c4732c23f1faabc4aed484 and the installed binary's cached
experimental schemas (WebSearchMode, ThreadItem/WebSearchAction and thread config).
Build/TypeScript, strict lint and static Python/source/schema review only; no
test suites, paid inference or user-session/VM runs were performed.

## Development authorization for v6 sessions (0.5.12)

The development coordinator and its workers now accept `studio-tools-v6` wherever
it inherits development capabilities from v5: build/deploy/run, VM start, check
completion and update operations. Previously the profile checks rejected these
calls before compilation despite enabled tool permissions. Existing frozen
permissions, project pins, revisions, worker identity and session ownership still
govern admission and worker execution. This requires no session/profile migration
or replay of a failed run. Idle coordinators adopt the installed release through
their existing mechanism; accepted workers retain their original release.
Build/TypeScript and lint only; no tests or project/agent/VM runs were performed.

## Session settings permission limit fix (0.5.11)

Remove the obsolete HTTP limit of 30 permission properties so sessions with the
31-tool v6 profile can save their settings. The existing store validates the exact
permission names and boolean values against each session's frozen profile.
The request body limit, revision checks and active-run guard remain in effect.
Build/TypeScript and lint only; no tests were run, as requested.

## GitHub project workflow and recovery (0.5.10)

New Project offers Create new and Import from GitHub. Select a named connection,
then a repository name/visibility and optional organization owner, or an existing
repository/branch to import. Private is the creation default. An organization
token can create under that organization when its policy permits; authentication
as a user does not imply permission to create repositories for that user's own
account. The connection name labels credentials; Repository owner selects the
actual GitHub namespace. The authorized R4OSDev flow was verified with one private
QA repository, two isolated Studio projects and actual upstream transfers.

Projects → GitHub in the second column groups status, saved-file diff, commit
author, Commit & Push and Pull. Commit descriptions are required; existing pending
commits retain theirs. Empty author fields independently use the authenticated
login and GitHub noreply address. After a failed transfer the original commit
remains available for an explicit push; reconciliation distinguishes a retained
commit from an intent that never published a ref. No automatic second commit,
force push, merge, rebase or stash is performed. Pull and opening Update use the
same SDK-validated fast-forward operation; Ignore preserves this opening's local
sources. Unsaved editor drafts are retained and block Pull. No-op recovery does
not mark editor content as updated. Case collisions in directory prefixes are
rejected during import as well as collisions in complete filenames.

Portable `.r4os-studio/project.json` carries checked app/component pins, never
host paths, UUIDs, credentials or sessions. Legacy imports require an explicit
matching local profile. Missing pinned tools must be installed separately;
repository setup scripts are never run as part of import. Session settings →
Tools → GitHub controls the separate push tool introduced in v6 sessions;
old conversations retain their native histories and require a new session for
the additive declaration. Since 0.8.31, new compatible sessions default Push on
when the repository is confirmed; existing Off choices stay intact. A
commitMessage is mandatory for every agent push.

The local daily backup's existing Projects source includes private `.studio/git`
objects, bindings, pull journals and receipts plus global `.studio/github` jobs.
Data/GitHub, including the named token catalogue, is outside its explicitly
selected sources. Restore with matching published host support and separately
re-establish the named connection/binding; inspect original uncertain jobs before
any remote action. Per-file/SQLite backup checks are not a global Git/catalogue/
GitHub transaction. Existing backup selection and VM scope are unchanged.

Final validation covers focused Git/recovery and permission failures, real
active-run FD handoff without inference, HTTP browser flows at1440/320px,
TypeScript/build and strict lint. Read-only/branch-protection/rate/network failures
are isolated fixtures, not policy changes to a live account. The exact QA repo
was deleted after ID/owner/name verification, followed by both own local projects;
the production repository and existing user project were checked separately.

## Agent GitHub push permission (0.5.9)

New project sessions use additive studio-tools-v6. Session settings → Tools →
GitHub offers Push project to GitHub. Its original default was Off; since 0.8.31
new compatible sessions default on with a confirmed repository. studio.push_project requires
commitMessage and optionally a bounded relative saved-file list. Enabled rights
are frozen for the accepted run. Existing v1–v5 and skill declarations/histories
are unchanged; older conversations show New session required for this tool.

The trusted sidecar runs outside the model/terminal namespace and passes the
active worker's inherited exclusive workspace descriptor to the private Git
coordinator via SCM_RIGHTS. Project/session/run, worker PID/birth, revision,
frozen profile/permission/pins and the real lock inode are checked at admission
and effect phases. Git shares the run's lifetime lease and existing workspace
lock; it neither fails on its own run nor opens an unprotected second writer.
Live terminals and development work must finish first. There is no agent Pull,
free remote selection, token access or general host Git/network capability.

The same checked manual push implementation binds the current saved snapshot,
creates at most the original commit and confirms its remote ancestry. The harness
waits on a stable run/call-derived job ID; result cards show its request and commit.
Unknown effects stop the run without automatic resubmission. Stop cancels only
the owned Git job and retains uncertain receipts/local commits for reconciliation.

Explicit local host compatibility setup:
`python3 App/scripts/agent-sessions/install-github-tool-support.py`, then install
the immutable release normally, then the same command with `--adopt` while idle.
The installer checks the exact previous updater source hash and adds only v6
compatibility; bootstrap/configuration, running workers, histories and VMs remain.
No downloaded privileged installer is executed and no service rights are widened.

Validation uses real SCM_RIGHTS descriptors, active-run/disabled/foreign-FD gates,
a real sandboxed local commit and simulated remote receipt without inference;
the shared upstream transfer path was separately verified against the authorized
own R4OSDev QA repository. The v5 declaration hash is frozen against0.5.8 and
unchanged. Required-description/argument/default-Off and updater rollback checks
plus browser enable/disable and legacy presentation cover the additive contract.

## Project opening: Update or Ignore (0.5.8)

Selecting a connected project or following/reloading its project/session link
checks the bound branch before mounting editable project content. Commit ancestry,
not timestamps, determines missing remote commits. Update and Ignore are the
explicit modal choices; Escape/backdrop cannot dismiss the decision. Ignore
keeps sources for this opening only. Internal view changes do not repeat checks;
reopening does. Fast-forward Update uses the same protected prepare/SDK/apply
pipeline as manual Pull. Divergence, dirty sources and editor drafts explain why
Update is unavailable. Failed checks show unknown status and allow local work.
Generation-bound requests and aborted stale reads prevent another project's
response from opening the wrong overlay. Generic project links now retain their
UUID through reload; existing native session links remain supported.

## Protected fast-forward pull (0.5.7)

Pull requires a clean saved index/workspace and no editor drafts. The same
repository identity and confirmed branch must be strictly behind its remote;
divergence, a missing branch, changed snapshots and active work block updates.
Preparation retains local ignored files, rejects incoming collisions and stages
the target Git blobs. The exact installed SDK checks the root app manifest,
language, technical name, application role and unchanged portable pins before
publication. No default selection or repository script replaces the project pins.

The existing unprivileged development coordinator now performs only the two fixed
import-finish/pull-validation adapters; it pins their release, serializes checks
and retains its existing permissions. This fixes authenticated import completion
without relaxing the web service's RestrictSUIDSGID/openat2 policy or exposing
GitHub credentials to SDK namespaces. Git and SDK validation stay separate.

Apply rechecks all files (including ignored files), project revision/pins,
repository revision and the exact approved remote commit under the project and
workspace leases. Atomic directory exchange retains the previous sources;
CAS-updated refs/index and a durable journal allow recovery after interruption.
New edits, runs, development work and deletion wait for unresolved source/ref
recovery. Open editor buffers are marked externally changed, never discarded.
Browser continuation retains original preparation/apply IDs across lost replies.
Ten focused Git cases include an interruption immediately after source exchange,
ignored-file retention, invalid approval rejection and dirty-source blocking.

## Manual commit and push (0.5.6)

Projects → GitHub requires a commit description and shows the saved file selection
before Commit & Push. The worker binds to repository revision and inspected
source hash, preserves editor drafts, uses the project's explicit author and
rejects diverged/behind history. Only the selected relative source paths enter
the private index, with literal Git path handling. Tokens remain brokered.

A local commit is recorded before updating HEAD; a separate single-ref push
never forces, follows tags or rewrites remote history. Confirmed remote ancestry
and durable original receipts distinguish success, Nothing to push and retained
local commits. Failed transfers keep local history. Reconciliation reads back
the original commit rather than creating another; an unobserved push leaves an
explicit pending commit for a later user action. Browser retries reuse the same
saved request, and worker death cannot silently repeat remote effects.

Live service validation also identified an unnecessary /proc mount in the SDK
import checker: systemd's protected mount namespace denies it. The checker now
uses an empty /proc directory while retaining its isolated read-only source and
catalogue, no network and all SDK manifest/plan checks. All four actual SDK
checks pass within the existing protected service namespace; no host permission
or service hardening is relaxed. Authenticated import is qualified again on this
release. Earlier published tags remain immutable.

## Project GitHub status and connection menu (0.5.5)

Projects → GitHub shows named connection/account, repository and branch,
local/remote commits, ahead/behind state, explicitly cached last check, saved
file changes and a128-KiB text diff preview. Refresh performs an authenticated
remote check; failures never claim a fresh remote state. File previews bind to
the inspected source snapshot. Unsaved editor drafts remain separate.
Existing projects can explicitly create a private user/organization repository
or bind a compatible existing history. Commit author accepts verified GitHub
noreply defaults or an explicit name/email. Form navigation and active jobs are
guarded. Original request IDs survive browser reload; uncertain mutations are
reconciled without generating another commit or repository. Read-only status
jobs do not hide an unresolved transfer from the last-operation view.

The live organization QA found that long production UUID/staging paths exceed
the Unix credential socket limit in0.5.4. The credential broker now uses a short
private temporary directory (including the service's private /tmp) and removes
it on completion. The socket remains ephemeral and token bytes stay private.
This also repairs authenticated import on long production paths; the immutable
0.5.4 tag retains the original implementation. Eight focused Git checks,
HTTP gates, TypeScript/build/lint and targeted browser validation apply.

## Import a GitHub app project (0.5.4)

New Project offers Create new and Import from GitHub. Import selects a verified
connection, repository and branch, fetches its full selected-branch history and
previews source identity and portable pins before registration. A fresh Studio
UUID and no VM/session assignment preserve the app's original technical name,
sources and component pins. A private additive catalogue mapping allows several
imports of the same module without renaming manifests; older releases cannot
build these new imports and fail their identity check. Existing projects retain
their original records. Publication uses the existing project recovery journal.

One supported root module.R4MF is required. SDK manifests/source paths are
validated by the exact locally checked SDK catalogue in a read-only namespace
without repository scripts or network. Missing pinned components/tools block
import; no default revision replaces portable pins. Legacy repositories require
an explicit local profile/language/module assignment. Links, submodules, LFS,
case-colliding names and oversized content produce preserved, bounded failures.
An interrupted job retains its original receipt and staging for reconciliation.

Repository owner in Create new additionally accepts an organization (for
example R4OSDev), explicitly requested during qualification. The server verifies
the organization and pins its ID before creating a private repository through
the organization endpoint. Connection authentication remains the token's user.
The historical 0.5.3 personal-account implementation is unchanged in its tag.

Validated: seven focused Git checks including real materialization, preserved
history/pins, rejected links and user/organization create recovery; one HTTP
security check; two isolated registrations using the actual installed pinned SDK
with duplicate module names/new UUIDs/idempotent completion; browser at1440/320px
on HTTP, build/TypeScript and strict lint. No successful remote import is claimed
by these isolated checks. Later release evidence records authorized live QA.

## Create a project with a GitHub repository (0.5.3)

New Project keeps local-only creation and adds verified GitHub connection,
separate repository name and Private/Public selection (Private by default).
Create project & repository creates an empty repository for the authenticated
user; the first upload is a separate Push with a commit message. Organization
repository creation is not part of this initial personal-account workflow.
The GitHub section in the second project column shows the binding and original
setup job; subsequent releases expand its synchronization controls.

Every newly generated project's source tree includes portable
`.r4os-studio/project.json` with language/module and checked component pins,
without local UUID, VM, credentials or host paths. Language-specific cache
ignores preserve Cargo.lock and other legitimate sources. Existing projects,
manifests, SDKs, compiler selections and native sessions are not rewritten.

Local creation and GitHub creation have separate durable request IDs. If GitHub
fails, retain/open the local project or correct a definitely failed remote setup
without making another local project. An uncertain create request is never
replayed: reconcile its original returned repository ID; a name match alone
cannot prove ownership after a lost reply. Reconciliation never deletes a repo.
Only supported host capabilities are offered. Focused isolated create/lost-reply
and portable-pin checks plus HTTP/browser/build/lint validation apply.

## Isolated project Git host (0.5.2)

The unprivileged Git coordinator accepts fixed project-bound jobs over a private
Unix socket. Explicit host setup: `python3 App/scripts/project-git/install.py`.
The installer adds only its own configuration, dispatcher and service; existing
bootstrap, VM/agent/development workers and stored connections are preserved.
Start the new service after installing this release. It adopts later immutable
host code at idle; accepted jobs keep their original release.

Jobs and object stores live outside Workspace under Projects/.studio/github and
each project's .studio/git. Git processes run in a separate namespace with only
their own source/object trees, fixed HTTPS, isolated configuration, disabled
hooks/filters/helpers and an ephemeral credential broker. Tokens stay in the
existing private catalogue and never enter URLs, logs or model/build namespaces.
Source inspection is limited to 10,000 files / 256 MiB / 32 MiB per file;
object storage to 512 MiB, two jobs total, one per project, 300 seconds per job.

Initialize, status, remote check and identity-bound connection jobs are available
through session/CSRF-protected Projects routes. Mutations share existing project
lifetime/workspace and busy guards. Original request hashes, progress, receipts,
Stop and readback reconciliation preserve uncertain effects without replay.
Create/import/commit/push/pull are subsequent release capabilities, not enabled
by this foundation. Validation includes actual unprivileged sandboxed Git,
project locks, request recovery and HTTP authorization; no real GitHub writes.

## GitHub repository accounts (0.5.1)

Saved connections now support freshly verified account selection and bounded,
paginated repository/branch discovery through protected `/api/github` endpoints.
Only allowlisted metadata leaves the host. Authentication, repository creation,
contents access and push rights remain separate; account verification never
claims permission to create a repository. Token replacement/removal invalidates
pending results; connection names are labels rather than repository owners.

The project binding contract records a stable repository/user/connection identity
and explicit branch. Private bindings live outside Workspace under
`.studio/git/binding.json`. Removing a connection used by projects requires
confirmation naming affected projects and preserves their sources/history.
Repository creation/import and Git execution follow in subsequent 0.5.X releases.
GitHub REST contract: 2026-03-10. Focused adapter/security/race checks, build,
TypeScript and strict lint are used for validation; no real repository mutations.

## GitHub settings HTTP fix (0.4.25)

Settings → GitHub now generates connection UUIDs with `crypto.getRandomValues`,
which is available on the Studio HTTP LAN origin. Opening the form previously
crashed because `crypto.randomUUID` requires a secure context. UUID v4 format
and private token storage are unchanged. This is a hotfix outside the completed
0.4.X roadmap; 0.5.X remains available for planning.

Validation: production build/TypeScript, strict lint and one focused browser
smoke on an insecure HTTP origin, including a mocked save with a valid UUID v4.
No automated test suite or real GitHub token changes.





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
chat/history, live file/terminal results, Send/Stop and Session settings. Ten
independent tool switches default on. Each explicit run maps to one native Codex
turn, with durable request identity and a frozen settings/pin snapshot. One run
uses a project's shared workspace at a time; the configured host limit defaults to 16 concurrent runs.
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
- Abgleichfehler lassen das Image unverändert erhalten und werden in Exchange angezeigt. Unterordner außerhalb von Build, ungültige Namen und überschrittene Dateigrenzen verhindern den Export; Image separat wiederherstellen, keine automatische FAT-Reparatur. Force stop kann ungespeicherte Daten verlieren oder FAT beschädigen.
- Exchange erlaubt ASCII-Dateien im Stamm und Unterordner unter Build, ohne Symlinks: 4096 Dateien, insgesamt 1 GiB Nutzdaten, 1024 Ordner und 16 Pfadebenen. Browser-Upload maximal 8 MiB je Datei. Upload/Remove/Settings werden im laufenden Betrieb gesperrt. Alte Austauschpartitionen werden beim nächsten vollständigen Stop/Start nach erfolgreichem Gastabgleich erhaltend auf 2 GiB vergrößert.
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
one run may use a project at a time, with a default of 16 active runs per host (existing explicit host settings are preserved). Native Codex
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
expire with the run. Up to four concurrent processes and 32 cached handles; completed
handles with collected output are retired while durable final status remains readable;
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

Exchange sync schema 2 stores files and empty directories under `Build`, with 4096 files/1 GiB, 1024 directories (since 0.6.55) and 16 path levels across the whole disk (since 0.6.56). Metadata and interrupted uploads count toward those limits. All traversals are bounded; extraction has an OS file-size limit. Conflicts preserve both host and guest trees. Publication exchanges two complete directories atomically with a durable inode journal, so recovery never repeats a completed exchange. Existing schema 1 baselines and legacy 257 MiB images remain readable. Older workers must preserve/block unsupported images or trees; stop/start a VM with the new worker before using the larger quota. Never change its pinned worker or edit `exchange.img` live. The browser displays the last offline host copy and permits stopped-VM uploads and individual file/empty-folder removal.

New deployment format `exchange-build-v1` uses a verified guest drive and `Build/P<7hex>/D<7hex>`. OWNER and DEPLOY receipts bind full project/deployment UUIDs and Exchange generation. PACKAGE is published last after full readback; deploy does not start the application. A private SFTP v3 metadata channel inventories all files, empty folders and stale transfer stages before reserving quota. The 1 GiB payload budget remains below the 2 GiB FAT capacity; an additional largest-file stage, receipt overhead and registered output allowance are reserved. Transfer reads have OS file-size limits. Capacity/ownership/type conflicts preserve everything. A running VM pinned to an older exporter needs an ordinary explicit Stop/Start, never a worker-pin rewrite. Deploy requires an already started VM and cannot bypass the separate VM-start permission. Old C: records remain historical and are never moved or deleted.

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


### Session-bound update agent tools and bundled knowledge (0.4.19)
New project sessions originally used the additive studio-tools-v5 profile with 30 tools, including twelve fixed update tools from planning/package build through native transfer/install, separate commit/proof and explicit recovery/cleanup. The browser presents their individual permissions in Session Settings. Since 0.8.31, new compatible sessions default commit and rollback on; saved earlier Off choices remain intact. Batch resume also requires the frozen commit permission. Skills never grant rights, and Skill Manager sessions retain their supported author tools. Existing profiles, native conversation histories and rollback protocol shapes remain supported.

The development broker checks the active peer/run/profile, frozen effect permission and every parent object's project/session provenance. Operator-created records remain operator scope. The harness publishes a durable pending job link, then waits on that original job outside model inference. It retries only read-only observation after coordinator unavailability, never admission or native writes. Unknown requests retain their original request IDs for the session's bounded jobs listing. No free-form VM/command/transport path or credential access is exposed.

The English R4OS Update Packages skill and complete reviewed guide are shipped under resources/skills with file hashes and exact source bindings. On server start a fixed private operation publishes it idempotently in the existing global Skills catalog. Only an untouched owned bundle is updated; user draft/published edits and per-session exceptions are preserved. Normal skill freezing and immutable resources apply.

Read-only verification returns native_batch_finalize_required promptly for the precise own rolled-back journal/rolling-back batch state. A new authorized resume action is still required. Historical job reconciliation can use its already persisted terminal proof after a later update supersedes VM ownership; no native mutation is replayed. Original errors/transport diagnostics stay recorded even when a later proof clears the current error.

Explicit root maintenance: python3 scripts/agent-sessions/install-update-tool-support.py qualifies the additive updater compatibility using the previous installed updater SHA-256 without changing worker units, bootstrap/configuration or VMs. After installing this immutable release, the same script with --adopt safely adopts the agent/development coordinators when idle; existing pinned worker services remain intact. Normal upgrades and old rollback release shapes remain compatible.


### Browser package workflow and qualification scope (0.4.20)
Project Settings → Run & Test includes Update packages without adding a main navigation item. Explicit metadata/requirements and native-confirmed artifacts create an immutable plan. The browser shows the qualified packer hash, exact payload/component versions/targets, package version and target OS release separately. Package build, assigned-VM preflight, Inbox upload/readback and transfer-group installation use existing durable jobs. Upload/install confirmation names the actual VM and every package/target; installation may apply live files during STAGE. There is no generic shell/network field or implicit VM start.

Original job cards display native preflight, complete-hash publication and immutable package receipts. The revision-checked saved update panel distinguishes installation proof, awaiting commit, unknown, abort and rollback. Separate commit/reboot, full-byte verification, transaction/batch resume, prepared abort, latest own rollback and terminal cleanup retain host guards. A freshly changed record must be reviewed again; failed/uncertain requests are never automatically resubmitted. Full original diagnostics are explicitly expandable. Session tool cards retain immediate job links and support native package status alongside the existing temporary Exchange deploy/run.

Qualification uses only the retained own QA projects and a dedicated explicit Full0.87.14 VM; productive VMs/defaults/pins remain unchanged. Native live R4X APPLY-on-STAGE, restart-required service COMMIT/reconnect/full inventory and bytes, recovery/abort/rollback/finalization, original lost-ack reconciliation and exact cleanup are evidenced across0.4.15–20. Controlled faults cover changed package/readback, upload/commit acknowledgement loss, foreign state, rights and unauthorized recovery. Batch bounds are16 packages/32 total components/32 total requirements, with same explicit target release and unique targets/package IDs. Dependencies are checked against actually installed state, never assumed available from a later package.

The SDK alone does not supply the complete Studio execution path. The minimal qualified R4UPack source closure, bounded native binary SFTP/text adapters and original-job/VM-lease/install/proof/recovery scripts are included. Existing pinned SSH, Zig and native guest SSHD/UpdateService are reused. No complete OS workspace or extra guest installer script is required. Native missing-target/LFN support and global commands without expected-batch/CAS remain practical limits; no full-OS update success is claimed. English guide: resources/skills/r4os-update-packages/references/Updates.txt, also maintained locally in Docs/Updates.txt.


### Read-only Codex credit balances (0.4.21)
The selected OpenAI account's existing usage section now includes Credits alongside earned resets. Each native rate-limit bucket may report hasCredits, unlimited and nullable balance text. Only those fields are projected. Bounded decimal/exponent text is retained exactly without JavaScript-number coercion; missing, invalid, null, zero and unlimited remain distinct. Identical reported snapshots share one display and are never summed across buckets. Credit units are neither earned reset counts nor general OpenAI API billing currency.

The existing account/rateLimits/read RPC, per-provider15-second cache, explicit refresh and visible-page minute refresh are reused. Sparse native notifications invalidate a full snapshot rather than filling missing fields with zero. A notification racing an in-flight read invalidates that response and permits at most one additional read; unstable/runtime-changed results are not cached or shown as current. Retired native clients cannot clear another client's cache. Reported account metadata changes clear cached usage, and account UI changes remount the usage view. Existing earned reset consumption remains a separate explicitly confirmed/idempotent action. Reading/refreshing credits never invokes a purchase, reset, reserve opt-in, email, inference or spend-setting mutation.

Source binding: local public Codex CLI/SDK/App Server checkout8c076942cb70fba8e5c4732c23f1faabc4aed484, protocol/v2/account.rs CreditsSnapshot/RateLimitSnapshot and offline protocol of qualified Codex0.163.0 SHA256399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215. This checkout is not claimed as complete desktop UI source. A reported balance does not prove spending authorization. The optional control capability is qualified separately; read-only display is the accepted scope.


### Qualified credit-control capability (0.4.22)
shared/openai-credit-capabilities.json records the reviewed public source revision/files/hashes, qualified0.163.0 binary hash and newly exported experimental ClientRequest schema hash. Offline schema/source inspection confirms the supported read RPC and no supported credit-spending enable/disable setter or state field. Reset consumption and the add-credits nudge email are different native operations and are never used to emulate a spending switch. No account request or inference is needed for this qualification.

The public Studio creditUsageControl capability is supported:false, enabled:null with an explicit unavailable-interface reason. Unknown spending state is not disabled. Native payload fields cannot spoof Studio capability. No spending-mutation HTTP route or local preference posing as a spending block exists. The UI explains the read-only scope; credit balances and existing reset controls remain independent. This fully satisfies the user's accepted read-only fallback. A future supported setter needs a separately reviewed adapter contract; no Codex fork/private API is introduced.


### Credits account switching and display qualification (0.4.23)
Account detail views are keyed by provider identity, connection state and reported account metadata. Usage effect generations invalidate delayed reads when their request context changes; an older finally handler cannot release a newer read or replace its loading state. Reset initiation invalidates older reads while preserving the original idempotency attempt. aria-busy exposes refresh progress. No inference/session history or native spending policy changes are required for credits in project or Skill Manager sessions.

Isolated browser provider fixtures qualify exact251-character decimal balances, equal buckets without addition, null/missing versus zero/unlimited, failed refresh with marked older values, delayed other-account replies, disconnect/reload, keyboard refresh and1440/320 layouts. Reset confirmation is opened/cancelled without redemption. Targeted backend tests additionally check fresh native reads after service restart and old retired-client notifications after reconnection; no real spending/reset/account mutation or paid inference is used. Existing-account read-only integration remains separately evidenced.

### Local daily backup support (0.4.24)
The independent local host timer runs at04:00 Europe/Berlin (Persistent=true, no randomized delay). Tools/Backup, outside this App repository, contains the fixed Python ZIP64 backup/isolated restore, explicit local installer and systemd templates. Sources are exactly App/Data/Projects, App/Data/LLMProvider, App/Data/R4OS, Docs, Research, Tools and central AGENTS.md. R4OS Images/Instances, shared project tools/helpers, project Development/Cache and private session Tools caches are excluded; installed toolchains/SDKs, pins, source, native history and confirmed artifacts remain. Other stores such as Data/GitHub and Data/Skills are outside this explicitly selected scope.

Actual CIFS mounting is required. Private staging, per-database online SQLite consistency, bounded stable ordinary files, no-follow symlink handling, manifest metadata/full hashes, complete remote readback and create-only atomic publication precede rotation. The destination is /mnt/storagebox/R4OS_Studio; at most three completed own dated archives remain. Mount/write/verification failures preserve previous archives, with no local fallback or rotation. No global atomic application snapshot is claimed. Restore targets a new isolated directory with optional numeric owner restoration; active data is never overwritten. No web/agent permissions or VM/Studio interruptions are added. Exact policy/setup/limits are maintained locally in Docs/Backups.md and Tools/Backup/README.md.

This release also centralizes usage-read invalidation in a stable callback so React cleanup remains equivalent and passes strict hook lint. The immutable0.4.23 tag retains its original warning; final account-switch/browser validation is repeated against0.4.24 before closing0.4.23.


### Goal restart and Stop recovery (0.6.27)

Coordinator adoption verifies the original Goal run/session/release, actual unit MainPID, process birth and UID. A lost start response retains the one durable admission; lost workers and original unconfirmed tool effects are never restarted or replayed. Late native Goal/turn notifications cannot undo Stop. Subsequent explicit Play freezes current account/model/effort/Fast Mode in the same native conversation and receives bounded unknown-effect references without tool arguments or credentials.

The explicit Goal status read uses a separate credential-free, network-isolated native process: initialize and thread/goal/get only, without resume/start/turn. It preserves original receipts and uncertainty; newer concurrent observations take precedence. Qualified with the pinned original Codex binary and deterministic local SSE replies,39 unprivileged focused Python cases, protected HTTP routes and browser reload/readback/explicit Stop. No model inference or paid calls.


### Private attachment upload foundation (0.6.28)

Project and Skill sessions accept bounded raw binary uploads through owner/session-bound authenticated routes, separate from Run JSON/SSE. Two uploads at most,16MiB per original; UUID bytes stay under private Sessions/<session>/Attachments, with additive metadata and original request fingerprints in Sessions.sqlite. Only fully received, hashed, checked and atomically published files are Ready. Lost replies read the same receipt; uncertain publication is never replayed. Draft removal keeps original bytes pending reference-aware cleanup.

PNG/JPEG/WebP use the explicitly installed qualified Pillow11.1.0 decoder in a networkless readonly namespace with512MiB/6CPU-/10wall-second limits,40MP/16384axis and one still frame. UTF8 source/HTML/SVG remain inert text/plain, maximum2MiB. Quotas are256MiB/256files per session and1GiB/2048files per owner, including retained removed/unknown bytes. Install locally with python3 scripts/install-attachment-support.py; --check is read-only. Web/updater never install root packages. Native delivery, PDF and composer controls follow their separately qualified stages. Eleven unprivileged NoNewPrivileges cases and project/skill HTTP tests include real partial-body abort, concurrency, replay, bounds and no Run/message/workspace creation.


### Actual native image messages (0.6.29)

Explicit Send accepts ordered Ready image IDs with text, image-only or mixed input. Original metadata/hashes and text are included in the request fingerprint; run, user item and immutable file references commit together. Retry returns the same Run. The worker verifies original bytes and exposes only accepted images from this session, including its previous sends, as individual readonly /attachments/<uuid> files. No unsent draft, private catalog or host path is exposed. Native localImage inputs retain the original clientUserMessageId; image bytes never enter Studio events or its small RPC input frames.

Actual selected ModelInfo input modalities qualify vision; explicit unsupported/invalid metadata rejects before start without changing model or files. Missing metadata uses only the qualified0.163.0 native text/image default. Historical image conversations also require vision support. Goal Play sends no draft attachments. A narrowly installed readonly dispatcher guard prevents older releases from starting an image conversation without its adapter; old text sessions and finalizers remain usable. Install only this guard locally with python3 scripts/install-attachment-support.py --agent-guard; no services/workers/VMs are restarted.

Qualified with60 unprivileged focused cases, four HTTP cases and the original native binary/actual Studio worker against deterministic network-isolated SSE: a3,151,221-byte PNG reaches native model input with identical pixels, image-only followed by the same native thread, no retry turn, no draft mount and maximum894-byte native notification. No paid/model inference. Text/PDF delivery and composer/history UI follow their separately qualified stages.

Native input modalities are frozen at admission and checked against the prepared catalog before the native process; stale public modality metadata is refreshed or rejected. Actual original-binary qualification includes PNG, JPEG and WebP and native completed UserMessage client IDs.


### Actual document inputs and readonly attachment broker (0.6.30)

UTF8 text/source/Markdown/JSON/CSV/logs and extracted PDF text reach the native turn as explicit document data. An8KiB initial excerpt carries file identity/hash and Unicode continuation cursor; the real user instruction stays separate in saved history. New project/Skill profiles10/3 add only studio_read_attachment, requiring its own permission plus Read file, a live owning Run/lease and an accepted reference in this exact session. Calls return at most12000 Unicode characters/32768bytes; original/derived hashes are checked. Draft/foreign UUID knowledge grants no read. Eleven historical tool declarations are unchanged; old profiles can use short inline documents and need a new compatible session for longer files.

Qualified Poppler25.03.0 runs in a fixed networkless readonly namespace with512MiB/10CPU-/15wall-second limits,128usable pages and2MiB extracted text. EOF covers available text only; truncated prefixes, missing scans/images and visual layout are explicit. Valid encrypted/scanned/unextractable/too-many-page originals remain private but readable:false and cannot be sent as read content. Derived bytes reserve quota before publication. No OCR/general Files API, execution or automatic workspace/Git/VM/Remote import.

Install the local PDF runtime with python3 scripts/install-attachment-support.py --pdf (--check --pdf is read-only). Explicit profile compatibility uses scripts/agent-sessions/install-document-tool-support.py; configuration/pins/old worker releases/VMs are preserved. Its --adopt only follows immutable installation and an idle coordinator. The fixed rollback guard now covers document references. Actual original Codex binary/Studio worker/new Skill3 profile with deterministic isolated SSE proves real PDF text, bounded source input and native broker continuation to an initially omitted marker, one original Send/Turn and no paid/model inference. Composer/history UI follow0.6.31/32.

### Composer attachments (0.6.31)

The session composer places Goal, model settings, Attach files and Send in the
Studio design. Multiple files, drop and pasted images use the same private
bounded upload pipeline. Cards show verified raster previews, progress, limits
and removal; HTML/SVG/PDF never render as active embeds. Only explicit Send
binds Ready compatible files. Goal Play leaves unsent drafts untouched.
Original upload/send IDs are persisted before POST; lost upload replies are
reconciled by receipt GETs, and explicit Send retry retains the exact original
ordered body. Text/Ready files survive reload and session/model switches.
Desktop, 768px and 320px browser checks use real HTTP/stores and a deterministic
native adapter without model inference. See Docs/Goal-Attachments.md.

### Attachment history and cleanup (0.6.32)

User message cards retain authenticated previews and original attachment downloads.
Bytes are rechecked against their original size/hash; SVG/HTML/PDF are never
active embeds. Stored uploads shows session usage and allows explicit removal
of unused uploads. Admission and cleanup serialize through the same SQLite lock.
Accepted refs, older run/message refs and uncertain/corrupt references retain
files. Durable removing plus bounded own-file deletion supports interrupted
cleanup without releasing quota prematurely. Original receipts remain retained.
Project backup/isolated restore uses the same seven sources; Skills stays excluded.
Native histories and their additional disk usage are not cleaned or counted as
raw upload bytes. Existing release bindings and worker file limits still apply.

### Goal/input contracts and human authority (0.6.33)

New runs compose a release-bound English input contract after unchanged saved
global/project/Skill prompt sources. A human Goal Play freezes the command
fingerprint, full objective capture hash and native thread. Worker/roadmap
sidecars verify the original accepted human instruction; document contents and
user-like item IDs do not establish it. Explicit Roadmap cleanup Goals can use
the existing archive/Docs/single-rollover workflow, while ordinary implementation
Goals cannot. Existing human message authority is checked against the original
Send fingerprint. Offline restore uses the same readonly provenance checks.
File manifests are lower-trust task data, preserve Send order and grant no
Goal/tool/Remote/transfer rights. Native Goal limits and input extraction limits
remain explicit; historical tools and saved prompt hashes remain unchanged.

### Goal and attachments accepted together (0.6.34)

Project and Skill sessions provide the two-row Goal UI, run model controls and
attachment paperclip in Studio colors, with responsive controls down to320px.
Save does not start work; explicit Play enables native continuation. Pause keeps
the current turn, Stop interrupts the owned run, and only explicit Send binds
Ready files. Original replies and historical files remain owner-bound.
The actual pinned native binary/Studio worker are qualified with deterministic
local protocol fixtures: a Goal reuses historical image inputs and reads past
documents through the real broker on the same thread, alongside native
continuation/Stop/limits/recovery. These checks use no model inference or paid
requests. Three isolated browser groups and authenticated HTTP checks pass.
See Docs/Goal-Attachments.md and the0.6.34 evidence matrix for scope and limits.

### Browser-only private Boards foundation (0.6.35)

Projects Boards use a separate private Boards/Boards.sqlite outside Workspace and
sessions. The fixed browser adapter/API requires Projects auth, Host/Origin/CSRF,
strict fields, parent UUIDs, revisions and durable original request IDs.
Creation, rename/description, list ordering and readonly original receipts are
available at /api/projects/:id/boards; the visible UI follows0.6.36. Initial
creation supplies three empty columns. Reads/updates do not initialize boards.
Atomic create-only storage, FULLsync, relational parent keys, feature-level
compatibility and bounded capacity preserve existing data on uncertainty.
No agent broker operations, tools or prompt hooks are added. Actual namespace
checks keep private Boards files and browser credentials out of native/terminal
views. Legacy projects require the separated Workspace layout first.

### Boards navigation and management (0.6.36)

Projects → Boards now shows +New Board above the project list. Create,
rename/description and Move Board use UUIDs, revisions and original receipts.
Project-specific selection/deep links survive reload; stale replies cannot
replace another project's view. Studio-styled columns have their own scroll
area down to320px. Save/Cancel/Escape and dirty/conflict handling preserve
drafts. Reviewing a conflict keeps edited fields and adopts new values for
untouched fields. Mutations are saved in sessionStorage before POST; recovery
reads the original receipt, with explicit same-body retry only. Controlled real
HTTP/browser checks cover lost replies, reload, concurrent edits and120-character
names without model, compiler or VM use. Card/column editing follows0.6.37.

### Board columns and cards (0.6.37)

Create/edit columns, quick Add card/Enter and card title/description dialogs are
available. Removing an occupied column requires an explicit same-board target
and atomically preserves all cards, including archived rows and their details.
At least one column remains. Card deletion names the actual card and requires
confirmation. Conflicts preserve drafts/untouched concurrent fields; independent
quick drafts and original receipts remain safe. Feature level2 and a declared
browser reader level protect older adapters/UI from misreading card data.
Thirteen targeted unprivileged cases, authenticated HTTP and desktop/320px
browser checks pass, without model, compiler, VM or source changes.

### Board moves (0.6.38)

Cards and columns have mouse drag grips with insertion markers and bounded
horizontal edge scrolling. Move dialogs offer the same exact destination and
position with keyboard and touch; touch scrolling starts no drag. Cancel/Escape
and foreign drops do not mutate data. No optimistic reorder precedes the saved
receipt. Focus and status announce a confirmed move.

One entity move freezes Board, order and entity revisions and the original card
source. SQLite updates source/target positions and the receipt atomically. The
server uses the full stored inventory, including archived cards, never a filtered
replacement list. IDs, notes and metadata survive. Lost responses read the
original receipt before any explicit same-request retry; conflicting order needs
Review current order. Search filters follow0.6.39 and will use Move for unambiguous
positions. No agent, workspace, model, build or VM operation is introduced.

### Board metadata and filters (0.6.39)

Card details include Low/Normal/High priority, an optional literal YYYY-MM-DD
calendar date, board-scoped labels and up to100 checklist items. Save/Cancel is
atomic; points keep their IDs when edited, checked or reordered. Cards show
checklist progress, label names, priority and due date. No reminders or agent
activity are triggered. Label rename keeps assignments; confirmed removal keeps
cards and checklist data. The fixed Studio palette does not replace label text.

Search reads the complete title/description in the private store, with bounded
Unicode casefold matching. Label, priority and due filters combine with search;
Clear filters and an empty result are explicit. Filtered views disable dragging
and retain exact full-inventory Move. Conflict review preserves edited fields
and refreshes untouched saved fields; checklist item revisions remain checked.
Metadata writes raise feature level3 atomically, blocking older adapters and
requiring older browser tabs to reload. Physical schema1 and existing IDs remain.
21 focused unprivileged cases, real HTTP and browser1440/320 checks passed,
including a leap date in Pacific/Honolulu and hidden-order-preserving filtered
Move. No model or VM run was needed.

### Board archives and lifecycle (0.6.40)

Boards and cards have separate archive/restore actions. Show archived exposes
archived entries; Board archive leaves every card's own state intact. Archived
contents remain readable; restore precedes edits. Permanent Board deletion names
its columns/cards/labels/checklist counts and cascades only the selected Board.
Original receipts remain available after deletion, so a lost reply does not
recreate or repeat the removal. Archive writes raise data/browser level4; physical
schema1 and existing stable IDs remain unchanged.

Visible views refresh every15 seconds and on focus. Saved changes never replace
an open local draft; revision review remains explicit. A removed current Board
keeps its draft and error instead of selecting another Board. A definite expired
auth rejection refreshes only the browser token; another user Save is required.
Boards hold shared project lifetime only, allowing manual edits beside active
agent/Goal/build and exclusive source locks, while confirmed project deletion
waits and removes only its own private data. Rename keeps UUID ownership.

The existing seven-source ZIP64 backup already takes an online SQLite snapshot
of private Projects databases. A real isolated backup/restore with a live Board
WAL and concurrent writes preserved IDs, archive flags, labels, checklist, dates,
receipts and0600. Sidecars are excluded. No backup source was added; restore does
not provide a global snapshot across databases/files. Real private Git status
still contains Workspace sources only. Corrupt schema, non-dense order or disk
failure preserve original data/request identity for inspection, with no automatic
repair or destructive replay. No native tool/profile or VM/remote state changed.

### Boards acceptance (0.6.41)

The integrated private Board workflow is qualified with separate owned browser
fixtures for CRUD/occupied-column transfer, actual mouse drag plus keyboard/touch
Move, checklist/labels/calendar/search/filter and archive/two-tab/recovery flows.
A search that observes a concurrent Board revision refreshes its snapshot before
showing results; filtered views keep exact full-inventory Move. New Board waits
for a current catalog snapshot after an accepted change. Local drafts,
original receipts and old-client guards remain in force.

All13 existing agent tool declarations, worker/broker sources and Goal/attachment
instructions are unchanged from0.6.34, before Boards. There is no Board tool or
prompt data. Real terminal, native and build namespace probes exclude private
Boards and browser auth; kernel network namespaces remain isolated. Busy
agent/Goal/build records and an exclusive source lock allow manual Board edits,
while lifetime protection blocks project deletion. No provider inference or user
VM/project run is part of this acceptance. Desktop/320px, keyboard, touch,
confirmed deletion, reload and protected data are checked. Full evidence and
limits remain in Docs/Project-Boards.md and local0.6.41 acceptance records.


0.7.6 prepares dormant native Goal capability for newly admitted compatible runs. Saved Active is paused before resume; ordinary completion remains ordinary. A separate immutable human Play ledger binds owner/session/run/thread/turn and the captured Goal without changing the original run request. Live control is reserved for the subsequent release; old workers keep their original capabilities.

0.7.7 enables explicit live Goal Save/Play through the original worker control channel. Save stays paused; Play preserves native usage and the original run snapshot. Acceptance and terminal completion share a database fence; lost replies are read, never resubmitted as another run. Original Codex protocol fixtures demonstrate native continuation after the initial ordinary turn.

0.7.8 exposes live Goal editing, paused Save and explicit Play in the browser. Matching worker capability and run/thread/turn binding are required. Original receipt recovery preserves drafts and prevents duplicate activation; Stop remains reachable in the editor.

0.7.9 completes live Goal recovery and authorization. Worker identity and claimed original commands survive coordinator reconstruction; unknown effects are never replayed. Captured live Play adds verifiable current human intent without changing the ordinary request. Backup/restore preserves its ledger; draft, Stop, queue and native usage behavior are qualified with isolated fixtures.

0.7.10 introduces private numeric statistics receipts, bounded per-session outboxes and a central lifetime SQLite aggregate under Projects/.studio/statistics. Protected read-only Global/project/session APIs preserve missing values, exact decimal token sums, original receipts and damaged storage. Goal and response measurements follow in the next releases.

0.7.11 measures each explicitly activated Goal execution using monotone worker/boot-bound checkpoints. Live activation excludes preceding ordinary work; pausing counts the current turn until it ends. A new Play starts a separate timer. Lost workers retain their last confirmed checkpoint as unknown; Global/project retain one lifetime maximum. A protected clock read endpoint exposes freshness for the later timer UI.

0.7.12 records exact per-response token usage from qualified Codex0.163.0 receipts. Bounded read-only native rollout backfill also covers resumed/older compatible runs without starting a provider. Runtime/thread/response identity deduplicates history and live receipts; cumulative snapshots, cache subsets and opaque metadata never add extra spending. Known usage survives failed/stopped work and missing coverage remains explicit.

0.7.13 adds System → Statistics with one navigation column and project → Statistics with two. Both display reported token totals/subsets, one longest Goal duration, coverage and update time. Stable deep links, visible-only refresh, reauthentication and unknown/unavailable states preserve existing navigation.

0.7.14 adds the Session statistics overlay beside Session settings and a Goal runtime in the first control row. The overlay contains only session token usage and preserves draft/focus/active Stop. The timer displays server-confirmed execution checkpoints, extrapolates only within their freshness window, freezes uncertain/end states and keeps hours above24.

0.7.15 completes statistics lifetime and restore handling. Bounded rotating reconciliation repairs an older aggregate from original source receipts without double credit. Project deletion retains undelivered numeric receipts outside the deleted UUID before removing it; Global and project lifetime values survive deletion. The existing Projects backup source includes these data; no Skill backup source is added.

0.7.16 adds complete skill deletion contracts and protected scope/confirmation/original-receipt APIs. A catalogue admission gate and per-skill lifetime/author locks protect active frozen references. Confirmed deletion uses a durable journal, atomic inode-bound staging and asynchronous safe cleanup; no runs are stopped. Numeric statistics and minimal deletion tombstones survive the removed private skill tree. The dialog follows in0.7.17.

0.7.17 adds the separate Delete skill action and named scope confirmation dialog. Cancel preserves local edits; active bindings remain independent. Original deletion receipts survive response loss and reload without resubmission. Confirmed success clears only typed Skill/session caches and returns to a neutral manager view.

0.7.18 completes full skill deletion qualification. Minimal UUID/source tombstones prevent automatic builtin resurrection after catalogue copies or bundle updates. Active published cross-owner references block deletion; confirmed finished history/copies remain intact. Attributed inactive runtime records and preferences are cleaned, while numeric lifetime statistics and existing backup boundaries remain intact.

0.7.19 introduces private per-session environment note storage and protected browser read/delete APIs. Typed bounded content, collection revisions, read-before-write, normalized dedupe and atomic call receipts preserve originals and prevent replay resurrection after deletion. Agent tools/settings and the overlay follow in0.7.20/21.

0.7.20: New compatible project/Skill Manager sessions default Environment notes on under Session settings → Tools. Frozen read/record tools report useful Studio observations selectively; application errors and routine permission/Stop responses are excluded. Old native conversations keep their original profile and require a new session for the two new tools. All16 prior declarations remain unchanged. Local call receipts prevent duplicate/deleted-note recreation; other tools retain their Unknown behavior. See `../Docs/Environment-Notes.md`.

0.7.21: Session header icons are Statistics → Environment notes → Settings. Notes pulse while any entries exist; reduced motion keeps a static count. The plaintext overlay supports bounded filters/pages and deletion while a run is active or note tools are off. Delete all confirms the current session/count; changed collections require a fresh confirmation. Lost responses recover the original receipt after reload, without an automatic second mutation. Local HTTP/SQLite browser checks1440/320 include project and Skill Manager sessions.

0.7.22 completes environment-note lifecycle integration. Existing full project/skill deletion includes its private note tables; only that owner's minimal browser requests are removed. The unchanged seven-source backup policy captures project Notes/collection/call/deletion data through online SQLite backup, including committed live-WAL rows. Isolated restore preserves deleted-call identity without recreation or inference; Skills remains excluded. Earlier native/tool history and separate backups are unchanged.

The qualified native lifecycle fixture activates a Goal on the same original worker, records a problem and a suggestion, deletes both, resumes the same thread with the original call and confirms no recreation, then confirms Off on the next run. Targeted store/queue/Stop/owner-delete/backup checks and browser1440/320 passed; other mutating tools retain their previous Unknown behavior. All fixtures use private synthetic data and owned local SSE, with no model inference.

For the additive profiles, prepare only the known updater compatibility with `python3 scripts/agent-sessions/install-environment-notes-support.py` as root before regular installation. After the immutable release is installed, run the same script with `--adopt` while idle; active original workers block adoption. Existing bootstrap, histories, VM services and component pins are preserved. See `../Docs/Environment-Notes.md` for the full operation and backup contract.

0.7.23: Project session transcripts follow the latest messages only at the actual bottom. The divider above “Message the agent…” pulses while following; scrolling up pauses, and reaching the bottom resumes. New messages, streamed deltas and late content resizing share the same follow state. Paused reading positions and composer drafts are preserved. Reduced motion uses a static highlighted divider. This is browser-only state; Skill Manager session behavior and run/provider/VM control are unchanged. Local HTTP/SSE browser checks1440/320, Build/TypeScript and lint passed without inference.

Project VM SSH (0.9.25): free commands on the assigned VM use the internal SSH transport, durable development jobs and a separate Tools switch; no build/deployment required. See [Project-VM-SSH.md](Project-VM-SSH.md). No guest function run was performed for this release.
# Common Studio runtime (0.10.1)

The [common runtime design](Agent-Runtime.md) defines one Studio-owned execution
loop for all direct model connections, reusing existing storage and tool brokers.
It also records required account boundaries and the transition from native
Codex/Claude sessions. Direct connectors and execution are delivered in the
following 0.10 releases; existing runs and saved conversations retain their
current runtime. Keep code simple and permanent checks tied to actual features.

## Claude browser subscription (0.10.27)

Choose **Claude · Pro / Max · Studio** to sign in in a browser and paste the
complete redirect address into Studio. No helper or local CLI is required.
Studio owns the private PKCE grant and coordinated renewal; existing native
Claude conversations and sign-in directories are preserved. The connector does
not import credentials from another installation or run a native agent. Sign-in
readiness is separate from real model and quota qualification. Disconnect clears
local tokens after original workers close; remote revocation is not confirmed.
The OAuth wire reference is the MIT-licensed
[opencode-anthropic-auth](https://github.com/ex-machina-co/opencode-anthropic-auth/tree/93cdd23b95f84a1d495744c2e6cc4058b5a86381).

### Claude model transport (0.10.28)

The same browser grant now connects to Studio's common Messages encoder, worker,
tool broker and conversation store. Account model metadata supplies capability
and token limits; missing facts remain explicit and can be configured manually.
OAuth compatibility adds the connector's required headers/system metadata and a
reversible tool-name namespace. Studio instructions and raw signed provider
history are preserved. The wire identity is compatibility metadata, not a native
SDK process. Native conversations are retained until explicitly converted.
Model work requires confirmation that account-level paid extra usage is disabled;
real subscription access and quota qualification remain separate acceptance work.

### Shared Claude account limits and session conversion (0.10.29)

The connection detail, navigation percentage and session limits use the same
private account reader and browser grant. One cache and original refresh receipt
keep both provider views synchronized; stale values are marked and an older
credential response cannot replace the current account. Opening the visible
account view reads limits when needed without inference. Model admission checks
only the required included-usage billing state, without requiring percentages or
enabling paid extra usage. Unsupported quota fields remain unknown alongside
the original private response.

Existing native sessions can be explicitly converted through the existing
preview and source/target hashes. Studio keeps session identity, original history,
confirmed effects and GOAL/queue boundaries. Installation and account sign-in do
not convert a session or merge accounts with the same email address. Actual
Claude login and direct model access still need their real acceptance evidence.
A populated native-session conversion is qualified below; fixture checks are not
subscription qualification.

### Native Claude archive compatibility (0.10.30)

Explicit conversion recognizes the native client's recorded context attachments
and API request/cache metadata. These remain in the hashed original archive;
embedded wire-message copies and tool summaries do not become conversation or
confirmed effects. Unknown formats, unmatched tool pairs and changed originals
still block conversion. A real owned native conversation exposed these records;
this compatibility check does not qualify a new Claude subscription grant.

### Z.AI Coding Plan Messages (0.10.31)

Choose Chat Completions or Messages in the existing Coding Plan connection.
Both use its saved key and account allowance; changing protocol does not rotate
the key or convert existing sessions. Review the session selection before its
next input. Messages uses the fixed /api/anthropic/v1 base and Studio's common
encoder, worker and tool broker. Only this Z.AI connector permits its documented
budget-free thinking and unsigned thinking blocks. Model metadata, original
quota holds and accepted queued inputs remain tied to their actual route.
The existing Chat model catalog is a metadata-only GET for both protocols; it
never substitutes a Chat inference for a Messages request. No prepaid fallback.

### Real Messages and native-history qualification (0.10.32)

Installed Studio completed real Z.AI Messages file creation, readback and a
same-session continuation, followed by an explicit switch to Chat Completions
with the same saved key, conversation and unchanged file. A disposable skill
conversation also completed real REA byte-entropy analysis through Messages.
Original model/tool records and account quota observations were retained before
regular deletion of the owned sessions, project, skill and temporary connection;
production REA and the existing Z.AI Chat connection were preserved.

A separate populated native Claude conversation was explicitly imported into
that same Studio session and continued with Z.AI, preserving its original archive
and confirmed effects. This does not qualify a new direct Claude browser grant.
Claude subscription qualification remains pending its own fresh sign-in.

### OpenRouter key budgets (0.10.33)

The existing model key also reads OpenRouter's current key budgets. Connection
details show reported USD caps, spend, remaining budget, reset interval/time
and BYOK inclusion. The navigation percentage uses the currently effective
budget reported by OpenRouter, falling back to its key cap only when no effective
budget is supplied. These caps are separate from account funding.

The detail and navigation share one account observation and refresh receipt.
Stale values are marked, unlimited/unknown values have no invented percentage,
and credential changes discard older replies. There is no management key,
second login, billing mutation or model request. The source is OpenRouter's
[current-key endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key).

### Shared Z.AI navigation allowance (0.10.34)

Every Coding Plan connection now shows its reported remaining model allowance
in navigation before opening its details. The percentage uses the lowest valid
5-hour/weekly model window from the same quota snapshot; unrelated tool request
quotas are excluded. Native credits remain separate from model tokens. Missing,
contradictory or unbound counters stay unknown; stale values have an asterisk
and actual access holds have an exclamation mark and remain visible in details.

The provider list reads the existing local quota cache. Opening either view
does not start a monitoring check or inference. One shared refresh replaces both
views, and older credential replies are discarded. The existing visible cache
read cadence is shared instead of running a separate detail poller; account
reads for OpenAI, Claude and OpenRouter retain their existing minute cadence.

Z.AI integer counters (0.10.35): The real monitoring response may report used
and remaining integer counters whose sum differs by one native unit from its
limit. The shared display permits that observed one-unit difference and uses
the original remaining/maximum ratio. Larger or fractional inconsistencies
remain unknown; source quota records and model/tool behavior are unchanged.

Public assistant and terminal deltas share a bounded buffer (64 events, 256 KiB including retained item projections, 100 ms). They become visible only after the existing FULL SQLite commit; non-stream events, model completion, tool admission and run cleanup drain pending originals first. Session history budgets use additive transactional counters in the same journal, including writes by older pinned workers.

Existing session, project and development catalogs open without claiming a SQLite writer slot. Session navigation reads a small summary; full configuration, context, runtime and receipts remain on-demand session details. Additive session/run/history indexes are initialized on the normal writer path; confirmed read requests perform no schema writes. Original lifetime and deletion gates remain active.

Coordinator metadata reads use the existing thread executor with four admitted jobs per host and no waiting queue. Each job owns its SQLite connections and lifetime guards through close; cancelled clients retain their slot until the real read ends. Periodic numeric reconciliation follows the same bounded path, and release adoption drains in-flight reads. Mutating admission, active process control and agent authorization keep their existing serialized paths.

Session event streams share a bounded read/cache path per typed owner and session (eight pages, 2 MiB, at most 32 queued distinct cursor reads). Dedicated event pages omit unused session details and carry a committed watermark. Replay drains to its captured watermark in bounded scheduling turns, while new events keep their live classification. Streams retain the 300 ms active cadence, authentication, heartbeats, reconnect cursors, 32-client admission and bounded response backpressure.

Session metadata now follows message/run/Goal/note events with a bounded visible recovery read every 30 seconds. Closed notes request only count/revision, with a one-note compatibility read on older coordinators. Shared scoped GETs coalesce model options and capabilities, invalidate on auth/provider/catalog/settings changes, and exclude original-request receipts and mutations. The Goal clock polls only while needed, keeps its native stale bound and interpolates qualified samples locally; hidden views start no idle reads. Independent provider families and session history/details load in parallel after their owner/auth binding is known.

Chat rendering batches durable deltas per frame, mounts tool details on demand, and pages long loaded transcripts without changing saved history. Live Studio answers announce their item before the first delta.

Studio continuation reads the confirmed checkpoint and required new records, retaining the exact latest human instruction. Bounded worker caches share validated records and one frozen wire request between estimation and dispatch; original archives remain available.

Heavy Studio views and dialogs load when opened, with guarded recovery that keeps drafts. Release builds include Brotli/gzip public assets; hashed assets use immutable caching while HTML is revalidated for the current release.

### Responsive Board reads and dragging (0.11.12)

Board overviews batch label assignments, checklist totals and card counts;
full descriptions and checklist text remain in the opened card detail. A small
protected metadata read checks the catalog revision and private database source
stamp during visible background reconciliation. An unchanged read retains the
usable snapshot, local forms and quick drafts. Explicit Refresh reads full data.
Database identity/stamp changes force a full read; schema, integrity, foreign-key,
order and mutation revision checks still run through the existing store.

Cards are grouped once per data/filter revision. Unchanged columns, card lists,
rows and filters retain their references. Drag geometry and hints are coalesced
per animation frame, identical hints keep their previous state, and Drop consumes
the latest pending hint before sending its original revision-bound mutation.
Keyboard Move, hidden/archived positions, original-request recovery and server
receipts retain authority over the result. Browser code manages interaction;
the existing private Board helper supplies verified reads and mutations.


### Roadmap reads and refresh

Roadmap pages aggregate exact task/acceptance status totals and subversion counts
for the bounded requested page. A browser revision probe can reuse a fully
verified unchanged file generation for at most30seconds, with at most64 project
scopes. Each probe still reads the actual project, schema, owner and coherent
revision/current version under the original project lifetime gates. Changed,
expired or unverified generations take the full integrity path; snapshot,
mutation, export and recovery checks remain complete. Private file facts never
leave the adapter. An opaque source marker also exposes equal-revision database
replacement independently in each browser.

After a project binding is known, overview and selected version load in parallel.
Unchanged background checks retain ready data and local drafts. Verification
errors or remote changes block new writes without clearing input. Explicit full
refresh retains the view until its response and disables inputs, including open
modal forms; mixed revision/source pages are rejected. Original mutation and
export receipts retain their existing recovery behavior.


### VM overview refresh

The VM overview reads systemd states in bounded batches of at most32 units,
matching replies by unit identity. Only active/starting units require QMP.
Missing state replies are errors rather than an assumed stopped VM. Every tick
still reads VM configuration and current service/share state. Display-only host
capabilities, image inventory and defaults can reuse an unchanged file identity
for at most30seconds. Profile, tool, template/drop-in, network and image changes
invalidate that metadata; explicit refresh bypasses it. Actual start, stop,
reset and release admissions retain their fresh checks and existing worker pins.

Visible polling shares one in-flight read. Manual refresh queues a fresh full
read behind an older poll. Leaving the view aborts its read and rejects late
answers; authentication changes invalidate the old result before obtaining a
fresh token. Mutations keep their original request and are never retried by
the polling helper. Hidden views start no idle overview reads.


### Component inventory and progress

Component views share one read at a time. Running jobs use the protected small
progress projection every2seconds; idle views check it every15seconds and read
inventory every30seconds. Hidden views start no periodic work. Manual inventory
refresh and version selection request a full check. A changed host/profile
generation loads matching inventory before new actions become available.

The component manager prepares inventory outside its state lock and applies it
only to the matching profile/catalog generation. Display reuse lasts at most
30seconds and tracks at most8192 identities of files/directories actually read
by the original verifiers, including SDK prerequisite and packer inputs. Changed,
missing, replaced or indirect inputs invalidate that read; uncacheable inputs
always take the original full path. Each response retains the actual inventory
check time. Job progress performs no inventory traversal or executable hashing.

Installation, default selection and execution still use their full original
validators. Read reuse cannot qualify an executable or alter existing SDK/worker
pins. Mutation admission and maintenance gates remain serialized. Original SDK
request IDs, expected profiles, payloads and durable receipt recovery remain
unchanged. A late poll cannot overwrite a confirmed mutation; failed refreshes
retain the prior inventory and selection, with new actions blocked until a
successful check. Changed-generation progress alone does not discard an original
pending SDK operation.


### Numeric statistics reconciliation

Numeric outbox delivery applies at most128 original receipts in one FULL target
transaction, preserving per-item conflicts and monotone Goal maxima. One grouped
source acknowledgement follows only after that target commit is confirmed and
matches each original key/payload. A changed source payload stays pending; a
lost commit response or a crash before source ACK replays the same numeric keys
without double credit. Fatal target failures roll the whole batch back.

The existing bounded coordinator worker retains every original owner/session
lifetime gate. Up to128 plain observations suppress redundant inactive-source
work for30seconds; active or unbound work still gets scanned. Source changes or
pending writes bypass the idle proof. Target loss/replacement and common restore
hints start a new archived sweep; periodic sweeps also cover in-place restores.
Each complete sweep advances in128-row chunks without an idle pause between
chunks. Explicit restore/delete reconciliation remains eager. No idle proof
authorizes a numeric write, and a racing source write invalidates the proof.

Scoped Goal-receipt and model-usage indexes avoid unrelated history scans. Goal
time reads join their original run flags in one query while retaining the
original config parsing, coverage and worker/clock checks. Existing receipts,
usage origins, uncertainty and historical Unknown states remain unchanged.

### Git inspection and local remote history

Git inspection and last-job projection run outside the coordinator state lock,
using up to four existing socket handler threads without another pool or queue.
Each actual agent inspection retains its inherited lease, frozen repository and
project lifetime checks, including final verification. Preview publication is
serialized per project so its original snapshot/selection quotas cannot race.
Release adoption waits for actual readers to finish. No read performs a remote
Git operation.

Last-job display keeps up to64 derived project projections/4MiB for five seconds.
New jobs, completion and reconciliation invalidate their project; selected
original-file and catalog identity changes invalidate reuse. Original uncertain
actions retain priority over completed actions and read jobs. A restart rebuilds
from original files and preserves unknown effects without replay.

Local Remote Host history uses a host/update/id index and one bounded merge of
33 candidates. Up to64 unchanged project/host summaries share a4MiB/30second
cache tied to full database/journal/WAL and directory identities. Changed,
replaced, indirect or invalid sources take original integrity verification;
project names and ready owners come from the current catalog. Each read holds
the original project lifetime gate. Cache entries contain display data only,
with no database handles, leases or execution authority. Existing bounded
background read work retains cancellation and release-adoption barriers.
Reviews, saved credential bindings and original results remain authoritative;
this local view starts no SSH check, job or model request.
