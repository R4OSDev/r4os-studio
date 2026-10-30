# Supported session tools default on (0.8.31)

New compatible project and skill sessions start with all their supported
permission keys on, including Commit update and Rollback. Push additionally
requires this project's confirmed private Studio repository binding. This also
applies to new sessions in existing projects. There is no migration of saved
sessions, explicit Off choices, native profiles, threads or frozen runs.

`tool_defaults.py` supplies the owner/profile-aware creation and Options values.
The context-free Push default remains off. The private local binding must be a
regular bounded, unlinked Studio metadata file with repository, account, branch
and positive revision. Portable Workspace metadata never grants permission.
An uncertain/failed/running repository-creation receipt does not enable Push;
a matching completed original creation must confirm its repository. Completed
imports publish the private binding only through the existing validated project
registration. Missing/invalid bindings remain off, without any remote query or
token check during local session creation/opening.

Defaults describe preferences, not current executability. Actual actions retain
their profile, provider, model, account, VM/host, lock, pin and revision checks.
API/unqualified Claude hosted web/image generation stays unavailable. Choosing
On starts no tool, VM, update/reboot, commit, push or inference. New settings
apply through the existing next-run admission rules.

The UI now has a typed `permissionToolLabels` catalog, distinct from transcript
labels. `Read environment notes` and `Record environment note` share the
existing **Environment notes** flag. `Generate image` uses **Image generation**.
None of these is a separate key in `permissions`. Their duplicate disabled
Files checkboxes were a display bug. Compatible v13 sessions such as Solitaire
Main need no new thread or profile upgrade for this correction. Existing
saved feature flags are shown once. Unsupported profiles/providers and unknown
image capability have concrete English explanations; a preference on does not
claim a currently qualified capability.

Five focused Python cases passed: real creation with/without a private binding,
portable metadata ignored, original Create replay after binding change, explicit
Off and frozen run preservation, failed/unknown creation, invalid/linked binding,
skill owner isolation and retained native declaration/default boundaries. The
actual SessionSettings browser passed at 1440/320 px with v13, legacy, unknown/
unavailable image facts, API/skill scopes, typed Save, conflict Reload and auth
rotation. No real push, update, image generation or model inference was used.
Build, frontend/backend TypeScript, ESLint and Python AST checks passed.

Evidence: `Research/R4OS/Roadmap-Implementation/0.8.31/` in the development
workspace. Milestone commit/push instructions are a separate 0.8.32 change.
