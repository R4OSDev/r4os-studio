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
