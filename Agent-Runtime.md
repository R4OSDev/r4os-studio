# Common Studio agent runtime

Version 0.10.1 fixes the design and transition boundary. Direct transports and
the common loop are delivered by the following 0.10 releases. Existing sessions
continue using their recorded runtime until an explicit supported transition.

## Ownership

The unprivileged Python run worker owns conversation state, input admission,
the model/tool loop, context, Goal, queue, cancellation and original receipts.
The existing Node transport code owns HTTP and streaming. A protocol connector
serializes requests and returns model events; it never executes tools or starts
another agent. Keep the existing Python/Node boundary instead of introducing a
framework, generic plugin host, new daemon or language.

The web server retains its protected API and durable SSE projection. The browser
renders those events and sends deliberate user actions. Neither runs inference.
Project and skill sessions use the same core, differentiated by their existing
typed owner and tool scope.

| Current responsibility | Common implementation | Boundary that remains |
| --- | --- | --- |
| Codex/Claude conversation files | Existing Sessions.sqlite extended with Studio-owned messages and checkpoints | Private original native history retained for import and provenance |
| Codex turn RPC and Claude SDK query | One Python model/tool loop | Responses, Chat Completions and Messages wire serialization |
| API Responses relay and Chat translation | Direct request from the common context | Required endpoint dialect and authentication |
| Worker.execute/bound_tool | Existing Studio tool catalog, dispatcher, permissions and receipts | Tool implementation and actual resource capability |
| Native Goal RPC and separate Claude Goal loop | Common Studio Goal state and continuation | Reported model usage and real account limits |
| MessageWorker/native steer | Existing inbox/queue at a common safe request boundary | An already-sent HTTP request cannot be rewritten |
| Native context compaction | Common prompt builder and confirmed local checkpoint | Supported content and actual context window |
| Native usage observers | Direct reported usage and existing statistics receipts | Provider-specific reported counters and quota endpoints |
| Native web/image tools | Existing Studio tool/asset lifecycle with an available configured service | Actual service access and feature capability |
| Stop and recovery | Existing process ownership, cgroup, receipt and Unknown rules | Actual original remote/process termination evidence |

## Small common contract

A session keeps its existing Studio UUID and owner. Each accepted input freezes
its request ID, connection/model/protocol and credential revision, instructions,
permissions, skills and ready attachments. External thread/turn/response IDs are
provenance, not the local conversation identity.

Messages contain ordered text, tool calls/results and supported asset references.
Required signed, encrypted or provider-specific reasoning is retained unchanged
with its route and original response. It is not replaced by a text projection or
forwarded to another provider as if it were portable.

The transport consumes a frozen connection, complete required context, selected
parameters and allowed tool definitions. It produces text deltas, complete
content, complete tool calls, reported usage, actual origin and a terminal
outcome. It accepts cancellation. The core alone dispatches tools and decides
whether to request another model response. Tool arguments are validated in full
before effects; a missing terminal frame never authorizes partial calls.

Completed, failed, interrupted and unknown retain their existing meanings.
Confirmed tool effects survive a later model failure. Repeated original calls
read their receipts; changed arguments conflict. Unknown work is never replayed
because a browser reconnects or a controller disappears.

Use the existing SQLite stores, durable events, SSE cursors and tool ledger.
Do not create a second transcript store or event-sourcing service. Necessary
additions are local and additive. Reads and upgrades never migrate sessions or
start saved goals automatically.

## Access is separate from model transport

| Connection | Direct common route | Remaining access constraint |
| --- | --- | --- |
| OpenAI API / compatible Responses | Responses | Explicit configured credentials and actual endpoint capabilities |
| ChatGPT/OpenAI Work plan | Responses when authorized for the direct route | Official Studio registration, granted inference scope and refresh; existing native credentials do not prove a new authorization |
| OpenRouter | Chat Completions | Existing routing, account/billing and original reasoning contract |
| Z.AI Coding Plan | Chat Completions | Existing subscription endpoint, approved OpenCode wire identity, original thinking and real quota windows |
| Custom / Ollama / LM Studio | Configured Responses or Chat Completions | Actual server capabilities; no discovery inference or model installation on open |
| Claude API / compatible Messages | Messages | Explicit API access; a Claude subscription alone does not establish API access |
| Claude subscription | A pure model route only if actually supported | Preserve the necessary native subscription path when no supported pure model transport exists; do not label it fully unified |

Account connection, catalog visibility and a completed inference are distinct
facts. Missing real access remains unavailable or unknown. The implementation
must not silently switch accounts, models, endpoints, billing or subscription
credentials to make a failed route succeed. Native exceptions are narrow and
explicit; they do not justify adding a new parallel agent engine.

The direct ChatGPT flow has its own registration and granted scopes. Browser
loopback and server loopback must be distinguished for a self-hosted web app.
Use the documented host flow; keep tokens outside browser storage, tool
namespaces, argv and logs. Do not copy native client IDs into a new client.

## Simplicity and qualification

All providers share the same core. Prefer one implementation per wire protocol;
keep only required authentication, quota and wire differences at the connector.
Reuse existing helpers and delete obsolete duplicate paths after their real
replacement and live references have been checked.

Only checks needed for an implemented feature belong in permanent product code.
This includes argument, permission, identity and protocol checks required for
correct effects. It excludes generic self-tests, model/version allowlists,
recurring probe inference, a new evaluation platform or a mandatory permanent
test matrix. Use focused existing validation for changed behavior; keep one-off
qualification scripts outside the repository.

No new model/version approval gate is part of this design. Unknown optional
metadata is not permission and does not automatically disqualify a model.
Reject only the operation whose required semantics cannot be preserved.

## Delivery boundaries

0.10.2 owns conversation storage; 0.10.3–5 implement the three direct protocols;
0.10.6 connects the common worker. 0.10.7–13 bring tools, context, Goal, input,
recovery, usage and optional media into that loop. 0.10.14 handles actual account
access; 0.10.15–17 provide explicit migration, switching and shared UI. 0.10.18
removes only truly obsolete native dependencies and qualifies the installed path.

Active runs keep their immutable release and accepted inputs. Existing native
histories and accounts are preserved. No user project, VM or SDK pin is a test
fixture. Preserve the ready production REA skill and its private runtime;
installed third-party sources/dependencies/programs remain excluded from Studio
Git and release archives.

Reference implementation: public Codex CLI/SDK/app-server source at
83086188ae0614bd882818ff1aa23f3194962012, especially core session/turn,
context management and tool dispatch; OpenCode at
501b15af26915ba52682e20e220e7e137e89e92f for existing connector behavior. Keep
upstream licenses if copying a necessary implementation; do not vendor either
complete codebase or claim the public checkout is the full desktop UI source.

Current access references:
[ChatGPT registration](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[direct plan limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations),
[Claude API authentication](https://platform.claude.com/docs/en/manage-claude/authentication),
[Claude Code credential boundary](https://code.claude.com/docs/en/legal-and-compliance).
