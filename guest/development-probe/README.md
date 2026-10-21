# Guest capability probe

Studio-owned qualification source using the official pinned SDK, not a kernel
patch or a normally installed guest component. Build with the matching Zig/SDK/
Contract profile in an isolated writable directory; the source SDK stays read-only.

The default mode exercises owned generation-bound process handles, rejects a
stale generation, reads the actual child's completed console output and exit7,
requests graceful close, observes a timeout and kills/reaps only its own child.
The child modes are test fixtures, not a remote shell. A passing probe is one
input to a version-bound Studio execution profile, not proof of arbitrary GUI,
service, driver, protocol, library or subsystem operation.

Upstream template provenance and licenses are retained alongside the source.
Compiled modules, images, credentials and run evidence are never committed here.
