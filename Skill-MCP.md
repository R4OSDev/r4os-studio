# Managed skill MCP transport

The private Python stdio client owns one managed child and original request
receipts. It negotiates the actual MCP protocol, offers no sampling, roots or
credential capabilities, and reads the complete paginated tool catalogue.
Tools retain their original input/output schemas and names. Resources, prompts,
completion and other advertised server methods use the same JSON-RPC transport;
optional client capabilities are never inferred from server capabilities.

Every request records its original ID and exact arguments before delivery. Raw
responses, hashes, complete structured results, text, image blocks and references
are retained together. Progress is associated with the original progress token.
A client timeout or cancellation sends the protocol cancellation notification
and continues observing that original request. A late response is retained as
such. Reading the same completed original ID returns its recorded result; a
pending or unknown ID cannot submit another effect. Malformed frames and EOF
keep outstanding tool outcomes unknown. Child exit confirms process termination,
not successful tool work or external target cleanup.

Private start vectors require an absolute managed executable and explicit
environment. A persisted process owner is never silently replaced. Stdin closes
first on shutdown, followed by bounded termination of the owned process group
when needed. Source text cannot select a host executable through this transport.
The shared model-facing broker verifies the frozen source/runtime manifest and
complete catalogue before use. Public skill text cannot choose a start vector.

Limits are explicit: 32 MiB per protocol frame and complete catalogue, 10,000
catalogue items, 1 MiB arguments and eight outstanding requests per process. An
oversized catalogue is rejected as incomplete. Complete accepted responses are
stored without truncation. Diagnostic stderr is bounded at 8 MiB and records its
actual received/kept sizes; this diagnostic limit is separate from result data.

REA 6.8.0 was built from its exact source commit in an independent private test
installation. The actual MCP process negotiated 2025-11-25, supplied all 234
canonical tool input schemas and six prompts, rejected invalid arguments, and
returned real byte-entropy analysis plus retained Evidence. Node 22.23.4 met its
advertised runtime engine range for this transport qualification; the managed
source recipe follows the source build's own `.nvmrc` (24.22.1). No provider
credentials or user project files were available to that test namespace.

Sessions use three regular tools: `studio_skill_discover`, `studio_skill_call`
and `studio_read_skill_result`. Their permissions appear in Session Settings
alongside existing tools. Discovery lists every native method, and selecting its
exact name yields its complete original schema. Native nullable/union arguments
travel as an unchanged JSON object in `argumentsJson`, avoiding provider schema
coercion. Codex, Claude and API models use the same broker and original receipts.

Accepted runs capture immutable runtime/catalogue references with the selected
skill UUID and package hash. Updates and later session choices cannot rewrite
that snapshot. Disconnected or disabled skills receive no runtime on the next
run. A runtime runs in a separate credential-free filesystem/network namespace,
with only the selected project and permitted attachments, immutable runtime and
private analysis state. Run command and Read file are required; the project is
read-only when Write file is disabled. No VM, host home or provider store is
exposed. Program prerequisites and further namespace/session-lifetime work are
qualified in their separately planned releases.

Whole original results stay private to the project/session and retain their
source commit. Results and schemas exceeding the model-facing page limit have
explicit UTF-8 byte cursors and a hash; reading them cannot repeat analysis.
Opaque references from other sessions fail. Original image blocks use the
existing native model image path when supported; any undelivered images stay
in the original result and are explicitly distinguished from visual inspection.

At the 0.9.51 implementation stage native process state is owned by the active
run, while result references remain session-owned. Full native session-state
continuity and final real-model acceptance remain open until the later lifecycle
and qualification work. A successfully downloaded REA source is still distinct
from its prepared managed runtime.

Protocol basis: [lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
[stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
[cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation).
