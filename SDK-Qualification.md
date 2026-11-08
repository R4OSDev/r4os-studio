Current execution model (0.12.2): SDK commands run directly as host Root with
actual per-job source/output/cache paths. The host network is available.
Namespace mounts and virtual roots described in the original qualification
below are historical; SDK pins, compiler policy and artifact checks retain
their purpose. The 0.12.2 own-data check exercised actual pinned Zig compilation,
PowerShell and SDK source maintenance through the direct command builders.

# SDK migration and qualification

Native Linux host evidence, 3 November 2026. The development path was qualified
after actual SDK migration and deletion of old operative SDKs under Studio
0.9.34 (`42b3dea3cd52a13c818de8fdf3c046da75c21155`). Release 0.9.35 packages
the final operating documentation, current agent guidance and an additional
retirement guard for descendants of the active SDK source directory.

## Exact package

- [Official SDK 0.64.145](https://github.com/R4OSDev/r4os-sdk/releases/tag/v0.64.145), source `56eb19bbebc8444b8766db9b80cc5f7ffd44218a`.
- SDK-Release.json SHA256: `1e34a86b810caa16dbda575f3e0116d246f84a4e5d157a7fe611b5d6baea2916`.
- Original Build profile: `6f0679f257b7f234bd9c2db1af0884fee043cec10801482d8ed4cb920c46a5f9`.
- Original Tools profile: `93e15d437faa75c3d82ef693d65dc0d4851db08464a6acc0a03b214f60bcbe8b`.
- Original Components profile: `ff75c5c5d586853b61ca5477b90040129578f36696fbc5a74fe473df0cb811fd`.
- Contract 0.64.73 / `c5a7989882385dd78ed2dcf5383c48bb4bed7b68`; Libraries 0.64.47 / `aeb023212ffa48b35849707589e4e37d356749ed`.
- SDK-selected Zig 0.16.0 and Rust/Cargo 1.99.0; separately verified PowerShell 7.6.7.

All official assets and required host tools were verified. SDK `Profile.ps1
Validate/Resolve` and complete `Package.ps1 Verify` succeeded. Upstream
qualification reports remain separate from the Studio runs below.

## Actual cutover and deletion

All four existing project source copies first built with the proposed new pins.
The journalled cutover migrated project SDK 0.64.127 and global SDK 0.64.134 to
the complete new set, including both private guest helpers and R4UPack. User
source bytes/modes outside generated SDK bindings were preserved. The first
operator attempt stopped before pin publication; the same request completed
with the local progress-manager correction shipped separately in 0.9.34.

After cutover, 299 obsolete SDK directories, operative source/tool/cache copies
and archives were deleted: 114130 files, 8004172131 bytes. Seven old installed
SDK revisions were removed. Current SDK-owned Recovery sources were preserved.
Fresh inventory found one managed SDK revision and no obsolete operative SDK
sources or SDK archives. No old SDK backup reserve was created. Original jobs,
confirmed artifacts, sessions and VM identities remained unchanged. The updater
requires SDK-only host compatibility after retirement.

## Studio's own Linux runs after retirement

Five temporary projects were created by native SDK templates and imported again
through Studio's normal import registration and validation. All five imports
built with the production Builder in a networkless namespace. Application,
library, driver and protocol families are represented across Zig, C and Rust;
this is not a claim that every catalog combination was executed.

| Case | Container | SDK profile | Artifact SHA256 |
| --- | --- | --- | --- |
| Zig library | R4L | `r4os-zig-module-v1` | `a860a43069fcb36714cf7259d6cce0592d60e3a8523af13d148f22bab36bce03` |
| C desktop | R4X | `r4os-c-module-v1` | `78b29b4e089401d5a821dc271fe6ca8d26baebd20d5df739eeddf0807f3b461c` |
| Rust terminal | R4X | `r4os-rust-r4x-v2` | `f9280584ec0d35b6ce63a4d0e441e6f503059da0239f43060e279bc65962d350` |
| Zig driver | R4D | `r4os-zig-module-v1` | `4bc1143ae168425ea11527ccb03aa33bf87e9723d3f490e9aad3a6962ea4d167` |
| Rust protocol | R4P | `r4os-rust-r4p-v1` | `d34143730a238562b97e6e15404ae2eb9c95fd89a014d5e14cb32581fa0b5aec` |
| Rust own libraries | R4X | `r4os-rust-r4x-v2` | `6b9e242e5b75f30c9958dc9855889a0de272db42d1de30edae0c6a3105c853c0` |
| Rust C companion | R4X | `r4os-rust-r4x-v2` | `ea5b19f65e7e82468dc4d10f1f5277d910db1f14f9eb8d04817bd740c5cd5e0e` |

The own-library run contains two pinned crates, a real transitive Cargo graph
and both dependency owners in compiler input receipts. The separate Rust/C
run calls its C companion and records its source and compiler in `native_c`.
Every success has a fresh native build receipt, container inspection and exact
artifact hash. Builds use `bwrap --unshare-net --clearenv`, readonly SDK roots,
offline Cargo and source-bound compiler caches.

The SDK-declared invocation uses `Build-Project.ps1` for Zig/C and
`Build-RustModule.ps1` for Rust, with `-ProjectRoot /workspace -SdkRoot /sdk`,
SDK-derived Contract/Libraries/additional-source arguments, `-ToolsRoot /tools
-ZigRoot /zig -InstallRoot /install -CacheRoot /cache/rust-build -OutputRoot
/output`. Native `Profile.ps1 Resolve` precedes compilation. Creation uses
`New-Project.ps1 -TemplateId` from the catalog; no free creator/build `-Profile`
parameter is invented. Full native receipts and the observed C invocation are
retained in local `Research/R4OS/SDK-Profiles/Implementation-2026-11-03/0.9.35/`.

Both private helpers were freshly built after retirement; no guest execution
was involved. Controller SHA256: `fab64f714c32d7f91772ffb64cc15079e078b1f4fe57708059060a0d1ace46a6`.
Watchdog SHA256: `9f163583433733a6e2f9e70760c2205f3143d7ebc3da50f1c9e70013eb76b0f9`.
The selected production packer was verified again with SDK profile and native
build-proof binding: `98f6ada91d1f13858348302e9ab18754ba7a7804ad4af2df2ae30e56990ff418`.

## Boundaries and limits

Eleven focused package/admission cases rejected changed profile/asset hashes,
unknown schema/IDs/references, casefold collisions, an incomplete package,
original legacy project pins, an unknown native profile and a changed private
tool cache. These checks did not start a compiler or install a legacy SDK.
Retirement preview also rejects a nested child of the active SDK directory.

A real missing Cargo dependency failed with `E0433` despite valid source pins;
no artifact was published or replaced by an older success. Earlier valid own-
library, transitive system-provider rejection, explicit technical Development
and stale-receipt evidence was reused rather than repeating large suites.
Ten focused component-policy/pin-publication checks, changed Python AST,
product build, frontend/backend TypeScript and ESLint passed. Actual HTTP
options expose the new SDK and SDK-derived catalog. Current instructions were
composed from four original readonly contexts: exactly one SDK paragraph and
unchanged saved source/configuration.

Windows has not been run. These are host build, package and migration proofs;
they do not establish guest application behavior, hardware/GPU operation or
cross-host binary identity. No existing user session, model turn, goal or VM
was started for qualification. Independent project-VM SSH acceptance remains
separate; its transport-loss/client-stop coverage is still open.
