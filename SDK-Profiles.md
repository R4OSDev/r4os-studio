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

The first migration release adds the new package contract and metadata
validation. Package provisioning, project migration, the final cutover and
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
