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
Session/runtime verification and the shared model-facing broker are integrated
in the following planned releases.

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

Protocol basis: [lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
[stdio](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
[cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation).
