# Compact development results (0.8.43)

New project sessions use studio-tools-v15. Its development results default to
a presentation JSON summary bounded to 12 KiB: original job/status/revision,
artifact identity/hash/size receipt, readiness, current checks/file findings,
actual exit status and cleanup/completion state. Repeated pins and inventories
are represented by identities and explicit detail references. Standard reads
request metadata only; previews do not advance the output cursor. Unknown
closure, readiness_unknown and exit_status_unavailable retain their existing
classification and original development.jobId/recovery scope.

read_development_job adds view=details, inventory or output only in v15. Details
and inventories return complete UTF-8 JSON fragments with a snapshot SHA-256,
revision and job/view-bound nextCursor. A changed snapshot rejects the old
cursor; reread its first page without repeating an effect. Inventory reads verify
the original artifact, including complete file/resource inventories. Output
reads use the original job and byte offset, with bounded serialized text; invalid
UTF-8 is preserved through an explicit base64 representation. Protocol envelopes
add their normal small metadata around the presentation limit.

Job pages distinguish totalBytes, pageBytes, nextOffset and hasMore from the
legacy truncated/captureLimitReached flag. captureTruncated is separately true
when a new worker actually discards excess captured bytes; historical unknown
values remain null. A metadata-only page consumes no bytes. UTF-8 character
boundaries are retained, and saved output is never rewritten for presentation.
The 65,536-of-119,419-byte case means another page exists, without capture loss.
Browser and older tool profiles keep their existing full job data shape, with
additive paging fields. All 19 existing declared profiles are byte-equivalent;
existing sessions, frozen runs and histories keep their original profile. Use a
new session for v15 detail views and compact defaults.

The update host needs a one-time additive v15 compatibility entry. The explicit
install-development-results-support.py maintenance script checks the reviewed
previous root-wrapper checksum, compiles the replacement, requires an idle
updater, keeps an atomic backup and restarts only the update service. It changes
no bootstrap configuration, agent/VM worker pins or data/protocol versions.
Older stable manifests remain accepted rollback targets. This maintenance is
local and explicit, never an automatically downloaded root installer.

Focused qualification: five projection/read cases, two original-log/capture
cases, seven existing exit/Goal recovery cases, existing HTTP scope/CSRF routes,
old/new profile declaration checks, Python AST and build/TypeScript/lint. The
representative large Unicode/pin/resource record is summarized without deleting
its detail pages. No model inference or user development job was run. Evidence:
Research/R4OS/Roadmap-Implementation/0.8.43/.

After the first v15 installation, a coordinator that still runs an older
protocol may need explicit idle adoption: run the installed
`python3 -B /opt/r4os-studio/current/scripts/agent-sessions/install-skill-support.py --adopt`.
The existing helper refuses active worker units or admitted busy runs before
restarting the coordinator. It preserves independent worker/VM units and all
session histories; no conversation profile is migrated. The normal v15
readback must confirm the coordinator version before finishing installation.
