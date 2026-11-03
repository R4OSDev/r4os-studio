# OpenRouter reasoning

## 0.9.38: strict routing and actual Crouton access

Native default tier/cache hints stay local. The OpenRouter wire omits these
endpoint-specific hints and an explicitly true parallel-call permission;
parallel calls remain allowed, rather than required. An explicit false control
is refused instead of being silently dropped. `require_parameters:true`, the
chosen backend order/allowlist and the saved fallback choice remain unchanged.
This avoids filtering out an endpoint for unsupported native default hints.

On03.11.2026 the existing Crouton manual entry was updated through regular
metadata refresh and versioned model save: `mandatory=true`, six documented
levels including `max`, no `none`, and the existing explicit default `minimal`
preserved. Normal session creation is available with the current Studio Codex
default. Connection/key/routing settings were retained.

The real acceptance remains open: the original0.9.37 request received HTTP404
without tool effects. Subsequent owned candidate requests reached Stealth but
received HTTP502, `Provider returned error`, with raw detail `ERROR`. A minimal
plain text request without tools or reasoning parameters received the same
provider error. These failures establish no successful model output, reasoning
roundtrip, file action or Crouton GOAL result. No substitute model is used to
close that acceptance and no account/privacy/routing setting is changed.

The old Goal/usage regression fixtures now supply current original thread/run
metadata and follow the current Studio runtime default. They no longer assert
the removed fixed runtime-pin gate. Actual original-run and spending bindings
remain required.

## 0.9.37: complete original history

OpenRouter reasoning uses the existing native Codex session, tool broker and
GOAL lifecycle over Chat Completions. Explicit documented effort choices are
sent through `reasoning.effort`; the implicit provider default omits this
parameter. Routing, explicit gateway fallback policy and `require_parameters`
remain unchanged. No model-name allowlist or automatic protocol switch is used.

Reasoning strings and structured text, summary and encrypted blocks are
assembled separately from visible text. IDs, formats, indices, signatures and
opaque data are preserved. Native history contains only an opaque reference;
the complete original record lives privately in that session’s
`Codex/OpenRouterReasoning/` directory. Records bind the owner, session,
provider, model and endpoint and retain the original configuration/credential
revision, engine hash, native/provider response IDs and assistant toolcalls.
File modes, ownership, record hashes and original call associations are checked
on reuse. Changes to an existing credential revision do not relabel old records.

Records survive worker/server restart with the same native thread. The native
local compaction path remains responsible for replacing its context; Studio
never invents replacement reasoning. Missing, changed or foreign references
fail precisely. Tool items are released only after the full response and
original reasoning record have been validated and durably saved. A lost final
frame or Stop does not authorize a replacement request or repeat a tool effect.
An incomplete token-budget finish retains actual usage and does not invent
visible text. Partial reasoning observations remain private and unconfirmed.

Limits are explicit failures: up to256 structured blocks and4MiB of assembled
reasoning per response,5MiB per private record,32768 private files and256MiB per
session ledger. No truncation or automatic eviction of required originals.
Session deletion uses the existing owned cleanup; no shared provider ledger.

This support is scoped to OpenRouter’s documented Chat Completions reasoning
contract. Other API/subscription adapters retain their existing contracts.
Real account/model access is verified separately by the Crouton acceptance.

## Metadata and selection, introduced in 0.9.36

OpenRouter model facts preserve `mandatory`, `supported_efforts`,
`default_effort` and `default_enabled`. Missing effort options mean there is no
effort selector; null means all documented gateway levels. The gateway levels
include `max`. Mandatory reasoning excludes `none`. An empty selection is the
provider default and must not be sent as `none`.

Metadata refresh keeps explicit manual model facts. Matching current reasoning
metadata is retained separately and any mismatch is visible. **Apply latest
reasoning metadata** opens a draft with those facts and preserves a valid
explicit default. Save uses the regular catalog revision and original request
receipt. Its private journal retains the previous and replacement model facts.
No refresh or save performs inference or rewrites existing sessions or frozen
run snapshots.

New automatically imported Crouton Alpha metadata provides the documented
`max` default. An explicit valid `minimal` default remains `minimal`.
Model metadata alone does not establish real account access. GOAL availability
follows the same effective adapter availability. In 0.9.36 the reasoning wire
support was still pending; 0.9.37 supplies that transport and history contract.

Official contract: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens

Studio uses the current configured Codex default for new sessions. No model
name or Codex version allowlist is added by this feature.
