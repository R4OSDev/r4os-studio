# Existing local and custom model servers (0.8.16)

System → Settings → LLM Provider → Local API offers **Server software**:
Custom, Ollama or LM Studio. Selecting software chooses the wire contract;
**Use local defaults** explicitly fills the address, Chat Completions and no-auth.
Nothing is contacted or saved until the corresponding user action.

| Software | Local default | Qualified scope |
| --- | --- | --- |
| Custom | Enter an exact allowed base URL | Existing generic Responses/Chat contracts |
| Ollama | `http://127.0.0.1:11434/v1` | Plain streamed text/functions; stateless Responses from0.13.3 |
| LM Studio | `http://127.0.0.1:1234/v1` | Plain streamed text/functions; Responses from0.3.29 |

Responses/Chat, optional bearer key and the complete reverse-proxy API prefix
remain explicit choices. Public HTTPS Custom API can also select the named
server contract. LAN/loopback requires Local API and an explicit allowed IP.
**127.0.0.1/localhost is the Studio host**, not the browser computer. The normal
worker checks reachability; no browser-to-server fallback or port/network scan
exists. No-auth omits Authorization; a configured bearer uses its original
private credential revision. LM Studio token auth requires0.4.0 or later.

## Metadata and model facts

Check connection performs one bounded GET `<base>/models` from the actual
unprivileged host helper. It never calls load/download/unload, starts a server,
changes model files/context/settings, signs in, scans installed model stores
or sends a generation request. Save/open/cache reads do not contact the target.
The Models response confirms only returned IDs; listed need not mean loaded.
Unsupported or missing capability fields remain unknown.

Use **Edit model facts / Add exact model ID** to declare exact text/function/
streaming support, reasoning/image facts and context. For named servers the
current scope requires an **explicitly nonreasoning model and the actual
server-configured context window**. The model's advertised maximum alone is
insufficient. Ollama's OpenAI endpoint cannot configure its context. Studio
does not create a Modelfile or alter LM Studio's context settings.

Reasoning/opaque tool history, images, hosted search/generation, Fast Mode and
native Goal are unavailable in these named adapters. This is visible before
admission; a responding server does not qualify every model. Custom retains its
separately qualified protocol behavior. No model IDs/default context values
are copied from OpenAI or guessed from names. A preset is an operator-selected
contract, not an automatic remote server-version/engine verification.

## Original history and transport

The server type defaults to Custom when reading an older record, without any
write/migration. Explicit saves persist it. New conversations bind it together
with original provider/base URL/protocol; changing that identity requires a new
session. Accepted Run/queue/metadata operations freeze their original profile,
configuration and credential revisions. Existing native threads stay intact.

Named adapters validate complete native text/function input, exact call IDs,
JSON arguments and matching acknowledged results. Developer instructions map
to the server's system role; conflicting system/developer priorities are
rejected. No history prefix, signed reasoning or unsupported generation control
is silently discarded. Stateless full history is resent on every request.
Ollama gets no previous_response_id/conversation/storage control; LM Studio
Responses gets store:false without remote state linkage. This describes request
semantics, not a guarantee about an external server's logging or truncation.

Native client telemetry, encrypted-reasoning include, default service-tier and
cache hints have no model-generation meaning in this plain contract and are
not forwarded. Chat retains reported usage and its validated completion
boundary. Ollama0.13.3 lacks tool-choice/parallel controls: only automatic tools
with parallel allowed are accepted. Forced/required choices and disabling
parallel calls fail before a POST. LM Studio uses the documented compatible
controls. No new context controller or tool executor replaces native Codex.

Actual context-overflow enforcement remains server dependent, particularly
older Ollama versions; context may be truncated remotely rather than rejected.
Studio cannot claim to detect such truncation. Returned structured overflow
errors remain errors. HTTP404 distinguishes a missing model/API route from
authentication; other status/body details stay masked. No automatic retries,
model/provider switches, auth fallbacks or repeated acknowledged tool effects.
TLS verification, complete-answer DNS scope checks/IP pinning, fixed prefix,
blocked control ports, no redirects and existing request/time limits remain.

## Verification and sources

Five isolated Python admission/store groups and two Node protocol groups cover
old-record preservation, frozen profiles, no-auth/bearer, capability gates,
original history and rejection of unsupported controls/tools. The protected
HTTP fixture checks strict field types. Eight actual pinned Codex0.163.0/Studio
worker cases in empty network namespaces cover both server profiles and both
protocols, project/skill, same-thread resume/queue/original tool receipts,
reverse-proxy prefix, context error, missing model, server end and Stop.
Four positive cases each execute one owned file write exactly once across two
runs/four POSTs; negative cases make one POST and no tool effect. Original
credential leases release only after native/transport closure. Separate actual
metadata-helper cases use eight GETs and no model-management/inference request.
Browser1440/320 checks presets, optional auth, custom prefix, Cancel, secret
lifetime, keyboard access and absence of automatic probes.

These are owned protocol receivers, **not installed Ollama/LM Studio engines or
real model inference**. A specific remote engine/model still needs its exact
operator-declared facts and a deliberately requested actual model run. No
software/model is installed or downloaded for verification. Evidence lives at
`Research/R4OS/Roadmap-Implementation/0.8.16/` in the workspace.

Primary sources checked30.10.2026:

- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [Ollama0.13.3 Responses source](https://github.com/ollama/ollama/blob/709f842457f40550c88da80f84bc8d7ba29371b9/openai/responses.go)
- [Ollama0.13.3 Chat source](https://github.com/ollama/ollama/blob/709f842457f40550c88da80f84bc8d7ba29371b9/openai/openai.go)
- [LM Studio Responses](https://lmstudio.ai/docs/developer/openai-compat/responses)
- [LM Studio Models](https://lmstudio.ai/docs/developer/openai-compat/models)
- [LM Studio authentication](https://lmstudio.ai/docs/developer/core/authentication)
- [LM Studio API changelog](https://lmstudio.ai/docs/developer/api-changelog)
