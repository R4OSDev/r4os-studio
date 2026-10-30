# Native Claude Subscription foundation (0.8.18)

This provider uses the unchanged native Claude Code runtime through the
Anthropic Agent SDK. It has a distinct `claude-subscription` identity, profile
revision and immutable provider/Studio-session/native-session binding. It is
not an Anthropic API-key connection, a Codex endpoint or an OpenCode harness.
Existing OpenAI/API records and Codex histories retain their original types.

The foundation provides private coordinator operations for identity creation,
original creation receipts, fixed runtime status and a metadata-only probe.
A created identity is **not connected**, has no account and is disabled.
Token/key/endpoint fields are rejected. No auth home is created on a read or
identity creation. Public HTTP/auth/session UI are subsequent stages.

## Pinned runtime and setup

`shared/claude-subscription-profile.json` pins every runtime byte and source:

| Component | Version | Archive SHA256 |
| --- | --- | --- |
| Official Agent SDK |0.3.312|`98a6c27b00b273fa0598b80540aa152d9fb58b6a1ac885b5993381e98469926d`|
| Official Linux x64 native package |0.3.312, Claude Code2.1.312|`5399c84c98bc4f04771815ef1a7b918ea02ef6e1faa28a2ba9de3ae2f7e6f405`|

The native executable is293592432 bytes, SHA256
`4f4178ce41d83e23341ebfbaecdbcf8ea6bf7baea0690025abe49eeec3a5d01d`.
Archives also retain their published SHA512 integrity pins. SDK21/native4
members and their individual hashes/sizes are fixed. Original license/README
files accompany the runtime; no vendor binary/source is added to this repo.

Explicit setup from the workspace root:

```sh
runuser -u r4os-studio -- python3 App/scripts/setup-claude-runtime.py
```

The installer requires Linux x86_64/glibc and an unprivileged writable private
provider directory. It downloads only these exact official packages; redirects,
links, unexpected members, wrong sizes and hash/integrity mismatches fail.
No npm scripts, plugin/latest installation, global CLI update or login occurs.
`--archives <directory>` reuses exact already downloaded SDK/Native archives
while retaining all checks. An existing valid profile is checked and reused;
a changed/incomplete one is preserved and reported rather than replaced.
Staging files/directories sync before a no-replace atomic publication.

Storage: `Data/LLMProvider/ClaudeRuntime/claude-code-sdk-0.3.312-v1/{sdk,native,profile.json}`.
Directories/executable use0700, data files0600, service owner/group. Entire
`Data/` stays ignored. This is separate from R4OS SDK/Contract/compiler pins.
Existing workers are not restarted and shared defaults are not changed.

## Adapter and control boundary

The SDK adapter provides bounded initialization, advertised-model/account
metadata control, interrupt and close. It uses an open async input stream
which submits **no user message**. Empty text is not a metadata operation.
Unknown controls, including Codex thread/turn RPC names, are rejected.
A failed/changed native stream closes the original query; no replacement
conversation or automatic replay is created.

SDK/session/message/provider-message/tool IDs remain distinct. A native TurnID
is unknown unless actually supplied by that protocol. Original SDK messages
remain on the private stream boundary with a bounded identity projection;
unknown types grant no permissions. Individual messages/controls are limited
to512KiB, metadata events to256 and control/close waits to12 seconds.

The fixed coordinator probe verifies installed pins, then starts only the
versioned Node entrypoint and native CLI in a filesystem/network namespace.
It sees empty private HOME/config/cwd, readonly SDK/native modules and no host
account/project files. SDK child environment replaces inherited variables;
API keys, gateways, cloud-provider/proxy credentials are not inherited.
Settings sources, native skills/plugins/MCP and built-in tools are disabled;
auto-update/telemetry are disabled and the permission callback denies tools.
Probe output is limited to64KiB and the process deadline to20 seconds. One
probe at a time; cleanup kills only its own process group/namespace if needed.
The web service gains no generic process/shell or VM-control operation.

Metadata alone proves neither an authenticated subscription nor per-model
entitlement. The native unauthenticated runtime advertises five models; these
are not offered as usable account choices. Native credentials will remain
managed by Claude Code in the dedicated auth stage; Studio does not copy them
into API keys, project workspaces, statistics or secondary secret stores.

## Plugin decision and staged capabilities

At the already reviewed immutable revisions, ex-machina1.8.6/93cdd23b95f8,
henadev0.3.0/1518c2526401 and griffinmartin3.0.0/4a397d95ce44 implement their
own OAuth/request adaptation. openchamber1.6.0/507cb87bfe9f and
khalilgharbaoui0.63.3/8a0032fd03f4 provide CLI/SDK/session/tool references.
Studio adopts the native CLI/SDK mechanism in its own bounded adapter.
No plugin code is copied, no OpenCode dependency/proxy/account rotation added.
The MIT repository licenses do not replace the native runtime's supplied terms.
Detailed comparison and original source hashes remain in workspace
`Research/R4OS/Claude-Subscription/Planning/` and `Docs/Claude-Subscription.md`.

Only offline initialization/model-metadata/account-metadata/idle-interrupt
are qualified here. Subscription authentication19, persistent model sessions
and Studio tool bridge20, quota/overage protection21, provider/model UI22 and
full lifecycle23 are separate work. Model turns, tools, Goal and overage
protection remain false in this foundation. Existing confirmed user approval
is recorded; no further approval gate is introduced. No account is connected
or real model inference performed by this setup/verification.

Five private-store/pin cases and three stream/control groups cover original
receipts, absent auth/key input, immutable identities, changed/linked bytes,
distinct message/tool IDs, empty input, environment isolation and changed
session failure. Actual SDK/CLI and own adapter probes initialize/read metadata/
interrupt/close under UID996 with no network or prompt. A separate service with
the current coordinator's512MiB/64-task/namespace protections passes in1.998s,
using152.8M peak memory and no swap. Normal build/TypeScript/lint and immutable
release/original-data verification apply. Evidence is in workspace
`Research/R4OS/Roadmap-Implementation/0.8.18/`.

Primary references:

- [Official SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript)
- [Native environment reference](https://code.claude.com/docs/en/env-vars)
- [Official SDK repository](https://github.com/anthropics/claude-agent-sdk-typescript)
- [Exact SDK package](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk/v/0.3.312)
- [openchamber source](https://github.com/openchamber/opencode-claude)
- [khalilgharbaoui source](https://github.com/khalilgharbaoui/opencode-claude-code-plugin)
