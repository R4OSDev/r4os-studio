# SDK profiles

The selected SDK owns build profiles, tools and system components through its
original `Profiles/Build.json`, `Profiles/Tools.json` and
`Profiles/Components.json`. Studio binds their exact bytes to the official
release, rather than creating a second set of profile defaults.

`SDK-Release.json` schema 1 uses the `r4os-sdk-package` interface. Its profile
sources contain paths, schemas and hashes. Capability schema 3 contains a
separate hash mapping; these are different contracts. The release and every
asset must match the published checksum list. Unknown formats, mixed sources,
conflicting identifiers and changed original bytes fail explicitly.

Studio's package adapter checks transport identities and cross-file bindings.
The SDK's `Profile.ps1` and `Package.ps1` own policy resolution, source-tree
verification and validation of derived tool exports. Derived INI, Cargo, Zig
and matched-tool files do not become independent profile authorities.

SDK build support and Studio runtime support are separate. A host template does
not imply a guest compiler or a VM test adapter. SDK build profiles are also
independent of Studio session tool permissions. Distribution profiles such as
Slim, Full and Test do not select an application build policy.

Package provisioning, project creation and isolated builds use the new package
contract. Existing project migration, the final cutover and
removal of old installed SDKs follow as separate roadmap steps. Historical
receipts retain their original identities. New SDK selection never falls back
to the retired `r4os-sdk-release`/DevKit metadata interface.

## Complete package provisioning

The component service downloads every asset from one selected official SDK
release, verifies archive identities and validates the complete source/tool set
with `Package.ps1 Verify`. Archive prefixes determine local roots. SDK sources,
Contract and Libraries retain their exact component identities; matching
Recovery snapshots and the matched tool export belong to the same package.

SDK `Setup.ps1` provisions and checks Zig; SDK `Rust.ps1 --profile sdk` provisions
and checks the private normal Rust toolchain. Optional kernel, graphics, boot
and VM tools are not required just to compile an ordinary application. Neither
global Rustup defaults nor running virtual machines are changed. Fully prepared
compiler files and links have a separate integrity inventory.

PowerShell 7 is a verified standalone host prerequisite, configured by the host
administrator in `Profiles/sdk-host.json`. Its original file hashes remain
bound; no SDK or compiler selection is inferred from that prerequisite. Existing
component hosts need the narrow `install-sdk-profile-support.py` maintenance
step to enable only their new package storage. The web process receives no
compiler, shell or additional root rights.

An interrupted preparation does not publish ready component markers. An explicit
retry checks the same package identity and existing bytes. Defaults commit only
after the complete package and required host tools have verified; a lost reply
does not initiate another activation.

## Projects and SDK selection

New projects and imports consume supported host templates from the SDK's
capability catalog. The official `New-Project.ps1` selects policy from the
template; Studio never adds a free `-Profile` switch to the creator or builder.
The SDK manifest plan and native profile resolver supply the effective profile
ID. That ID, the original three hashes and the template identity are retained
with the ready project and its portable metadata. Preparation and publication
share the existing recoverable creation journal.

Project settings select a complete SDK package. Compiler, Contract, Libraries
and matched tools are derived read-only values, including for imported projects.
Legacy portable pins require explicit migration. Old data can be inspected but
does not select a legacy runtime when a new package is unavailable.

Project hosts keep shared SDK packages read-only. SDK helpers receive a private
exact copy of the matched tool export because they prepare executable modes in
`ToolsRoot`. Source verification runs in private project work directories.
An unchanged-input signature reuses the original native package verification;
changed inputs return to the SDK verifier. It does not normalize sources or
resolve policy in Studio. Compiler file and link inventories remain separately
bound, and actual module resolution remains native SDK work.

Component publication stages each extraction inside its destination directory.
This preserves atomic rename with separate systemd `ReadWritePaths` mounts.
An explicitly retried failed SDK operation retains its original failure history.

## Isolated builds

Zig, C and Rust use the host build drivers declared by the selected SDK's
capability catalog: `Build-Project.ps1` for C/Zig and `Build-RustModule.ps1`
for Rust. Studio freezes
the source snapshot and SDK bindings, asks the native catalog and resolver to
validate the module profile, and runs the SDK driver in the existing networkless
worker namespace. There is no retry through a direct Zig builder, old SDK or
independently selected compiler.

Every successful artifact has a fresh native `Output/build.json` receipt. Studio
checks success, module identity, effective profile ID, all three original hashes,
SDK/Contract source commits and actual artifact bytes/SHA-256. Rust also binds
the captured Cargo lock. Failed builds never publish an older artifact as a new
success. Compiler cache identity includes the exact captured source hash.

SDK catalog and container inspection use the verified matched tool export.
The optional Studio update-identity adapter uses the SDK's own host-tool profile
and optimization policy. Agent tool namespaces expose the same SDK, Libraries,
private matched tools and install root; a retired global Rustup alias does not
choose a compiler.

## Own libraries

Select explicit additional inputs in `.studio/sdk-inputs.json` in the project
workspace. Its schema is 1. `additionalLibraries` is an array of the SDK's own
records, with workspace-relative `root` paths:

```json
{
  "schema": 1,
  "additionalLibraries": [
    {"id": "my-library", "root": "vendor/my-library", "commit": "FULL_40_CHARACTER_GIT_COMMIT"}
  ]
}
```

A record may instead contain the SDK vendored `tree` identity: algorithm
`r4os-files-sha256-lf-v1`, complete relative `files` and `sha256`. Use the selected
SDK's `Get-R4SdkTreeDigest` helper to create that identity; Studio does not
implement another source normalizer. An optional `path` selects a subdirectory
inside the pinned root. Source paths must be real directories inside this
workspace. Git inputs require standalone checkouts. Selected Git object/index
metadata is captured without config, hooks, logs or alternate object stores;
executable source modes are preserved. Symlinks, hardlinks, missing files and
incomplete vendored inventories fail before compilation.

Source pins do not add an import or a Cargo dependency. Declare those edges in
the actual project manifests and Cargo lock, including all transitive sources.
Rust path libraries inside the application directory must be excluded from the
application's Cargo workspace: the SDK requires exactly one application member.
For example, use `exclude = ["vendor/my-library"]` under `[workspace]`.
Studio passes actual `DependencyRootsJson` as a JSON array string to the SDK.
The native SDK validates reserved provider IDs, aliases and the real offline
Cargo graph. A source pin alone never becomes evidence of a linked library.

Build admission freezes the exact selection. Capture binds all bytes and source
permissions to its receipt. A changed selection requires a new build request;
repeating an old request does not select new sources. The compiler cache includes
the complete snapshot identity. Run & Test shows the selected libraries and
source mode; each job exposes its original native source resolution.

## Explicit Development profiles

Development uses a real standalone SDK Git checkout in this workspace and an
explicitly generated native receipt. In the existing project Terminal namespace,
for example:

```sh
pwsh -NoLogo -NoProfile -File /workspace/development/SDK/Tools/Profile.ps1 \
  -Action Develop -SdkRoot /workspace/development/SDK \
  -Profile r4os-rust-r4x-v2 -ContractRoot /contract -LibrariesRoot /libraries \
  -Output /workspace/.studio/development-rust.json
```

Select the module's actual SDK profile ID. `Develop` requires a new output file;
Studio never invokes it to repair a stale receipt. Select that receipt explicitly:

```json
{
  "schema": 1,
  "development": {
    "sdkRoot": "development/SDK",
    "profile": ".studio/development-rust.json"
  }
}
```

Optional `contractRoot` and `librariesRoot` are also workspace-relative. Without
them the SDK package's exact `/contract` and `/libraries` sources are used.
Generate the receipt with the same stable namespace roots used by Terminal and
builds. If needed, run only the selected SDK's `Sync-ComponentPins.ps1` explicitly
to update generated Zig component pins; no independent historical compiler or
optimization choices are written by Studio.

The SDK validates the selected receipt, current Git commit, source tree and all
three profile hashes before compilation. A changed source, commit or profile
fails as stale. Builds pass `DevelopmentProfile` and `Technical` explicitly and
remain technical in the API, job card and artifact proof. The original receipt,
its SHA-256, native resolution and actual compiler graph remain bound. Such
artifacts receive no regular qualified update identity. Matched-tool source and
profile checks still apply; selecting Development does not qualify arbitrary
SDK/system-library changes or generate replacement tool exports.

`R4OS_SDK_DEVELOPMENT_PROFILE` may name an explicitly selected receipt in direct
SDK use. Studio build workers clear ambient environment and pass the selected
receipt as a parameter. Neither its absence nor a validation failure activates
the old SDK system.


## Explicit whole-project migration

`scripts/projects/migrate-sdk.py --apply` coordinates the cutover with a stable
request ID, exact installed SDK revision and previously successful staged build
qualifications. It gates project and component admission, requires idle projects
and workers, and holds every original project lifetime/workspace lease. It never
starts or stops a session, goal, model run, guest command or VM.

Each project keeps a durable pin-change journal. Immutable no-follow source
capture precedes SDK `Sync-ComponentPins.ps1` and SDK-selected offline Cargo lock
synchronization. A Zig SDK dependency changes only when its original URL/hash
matches the old or selected SDK identity. User source changes after preparation
block publication. Generated files, portable metadata and catalog pins publish
under their original gate; a partial publication rolls forward from the same
receipts without rerunning SDK maintenance or incrementing the revision twice.

The operator verifies that successful staged artifacts used exactly the proposed
source bytes and new pins. It prepares both private guest helpers and the packer,
publishes every project, then activates the original durable SDK default request.
Global gates remain until the final inventory agrees. A failed or interrupted
migration stays pending for its original request; no old SDK fallback is chosen.

Private guest helpers derive pins from the accepted project's SDK, including
its Libraries and native module profile. They use the SDK manifest build driver;
obsolete private direct-build files no longer select an older SDK. R4UPack retains
the independent Distribution source identity while its SDK source, Zig compiler,
host profile and optimization come from the selected SDK package. Its actual
native build proof and binary SHA-256 are bound to its installation marker.

`setup-r4os.py` now prepares a complete official SDK through the existing
component host. It has no legacy archive/minimal-profile installer and does not
change project pins or activate a different standard automatically.
