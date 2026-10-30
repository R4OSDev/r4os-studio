# Native Claude sessions and Studio tools (0.8.20)

The pinned, unmodified Claude Code 2.1.312 / Agent SDK 0.3.312 now has a
separate persistent session worker. It does not emulate Codex RPCs or invent
native turn IDs. A Studio session owns one immutable native UUID, its original
private transcript, account identity and runtime pins. Creation and the
original request receipt share a transaction; retries retain the same UUID.

Native project histories are mounted separately from the provider's private
authentication home. The SDK alone manages transcripts, resume and compaction.
Closed original result receipts and byte inventories gate resume. Missing,
changed, incomplete or unconfirmed history preserves existing bytes and blocks
execution; Studio never reconstructs a native conversation from displayed text.

## Tool boundary

The native process has no project workspace, SDK source, other provider home or
general host/VM mounts. Native file, shell, web, agent, scheduler, memory,
plugin and computer tools are excluded. One fixed private stdio MCP server
offers exactly the frozen project v14 or skill v5 Studio tool catalog.
Deferred native tool search and background compaction precomputation are
disabled. Native runtime/schema/provenance checks must complete before input.

Native PreToolUse and permission callbacks bind the original native tool-use
ID, argument hash, session, owner, provider, request and worker. A private host
grant is required before the common Studio dispatcher checks the original
schema, saved permissions, current binding and durable intent/result receipts.
The existing file, terminal, development, GUI, roadmap, skill and note handlers
remain authoritative. Repeated confirmed IDs replay their receipt; unknown
effects never execute again automatically.

Four existing root-union schemas need a transport envelope because the pinned
native MCP client otherwise omits them. Only their wire form becomes
`{request: originalArguments}`. The envelope is removed before the original
Studio validation/dispatcher; all original branches and references remain.
Native MCP result thresholds cover the bounded original Studio result instead
of silently writing it to a file that the model cannot read. PNG evidence is
returned as an image block; Studio retains its opaque evidence reference.

## Stream and lifecycle

Text deltas and final snapshots retain separate provider-message/block
identities. Tool items retain their original call IDs and common results.
Compaction is a native status event. The pinned protocol offers raw thinking
blocks but no separately qualified reasoning-summary channel, so raw thinking,
signatures and private provider errors are excluded from display. Usage
accounting and richer lifecycle behavior belong to the subsequent stages.

Stop closes tool admission before native interrupt. The host waits for its own
native process and original closing receipt. A confirmed stopped process may
still lack a native result: the run is interrupted, while its history stays
protected until explicitly reconciled. Credential leases bind provider/account
revision, owner, session, run, request, runtime and worker PID/birth/release;
authentication changes cannot race active or unconfirmed leases.

## Qualification and remaining stages

Own filesystem/network-isolated protocol fixtures execute the actual pinned
SDK/CLI with synthetic credentials and a local fake Messages endpoint. They
prove project and skill execution/resume, native reactive compaction and resume,
streaming, permission denial, Stop, root-union dispatch, a 150,028-character
original result and PNG delivery. A repeated tool ID across two workers causes
one fixture effect. These are protocol checks, not a real subscription login,
billing proof, R4OS project build or guest test.

Model admission remains closed by default. The worker cannot send a model
prompt without the separate positive native account and disabled-overage
admission proof. Quota/overage policy (0.8.21), public model eligibility (0.8.22)
and final Goal/queue/recovery/deletion/account acceptance (0.8.23 and open
0.8.19 checks) remain separate. Existing Codex/API sessions retain their original
engines, histories, credentials and pins.
