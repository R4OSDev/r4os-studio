# API session lifecycle and usage (0.8.17, partial)

Project/Skill API sessions keep the original native engine, current frozen
Studio/Agents.md or Skill Manager instructions, selected skill resources,
tool namespaces and rights. Function transport delegates to the existing
file/terminal/build/deploy brokers and original tool ledger. A provider does
not grant shell, host, VM or development permissions. No new build runner or
VM adapter is introduced. Existing project pins and native histories stay fixed.

Neutral API model descriptors explicitly restrict image input and hosted native
extras. Image capture/inspection rejects an unqualified model before calling
the development broker; unsupported image attachments, hosted web/generation,
Fast Mode and native Goal cannot silently fall through to text. Text/PDF
attachment references retain the existing extraction/size/read-tool contract;
unsupported opaque content fails rather than being dropped by the adapter.
Guest build/deploy/GUI success is not newly claimed for each model provider.

## Authoritative API usage

The native binary normalizes some omitted usage subcounters to zero. For API
statistics this is insufficient evidence that a provider actually reported zero.
The private model relay now observes **only explicit wire counters**, separately
from forwarding Responses or translating Chat. Responses SSE observation is
bounded, handles split UTF8/events and does not alter the stream or execute tools.
Chat uses its already validated terminal usage. Each original request produces
at most one bounded usage observation, with a maximum256 per Run. Missing,
invalid, oversized or incomplete observations remain unknown.

The original worker drains its own relay before persisting private
`statistic_api_wire` records. An actual native response-completion or retained
native usage record must match the original Run/thread/response. Only then are
the reported total/input/output and present cache/reasoning subfields ingested.
A live API run defers statistics until its transport closes; no history cursor
advances ahead of these original observations. Known numbers survive later
failure; missing data produces coverage gaps. No token estimate is made from
text, native default zeros, cumulative events or requested model metadata.

The existing spend key (`codex-response-v1`, pinned runtime, native thread and
response) remains unchanged. This preserves previously acknowledged numeric
receipts and avoids new credit during restore/reconciliation. A private
`statistic_api_origins` record adds the frozen provider/kind/protocol/server,
adapter identity, revisions, requested model and original thread/response.
Chat response IDs are explicitly **local transport IDs**; they are not provider
billing receipts. OpenRouter's reported model/backend/original response IDs
remain its separate Run-bound observations. Missing origin evidence stays
unknown; conflicting evidence preserves the original and marks a gap.

Provider credentials/URLs/headers/prompts are absent from these new records.
Only numeric receipts and hashed scope/response identities reach project/global
aggregates. No historical numbers or subscription receipts are rewritten.
Earlier API responses without original wire evidence retain existing receipts
and gain no invented values. API-specific tables are created only for relevant
API work and participate in the existing session-scoped deletion.

## Queue, stop, rotation, deletion and restore

Accepted input retains its original provider/config/credential/model/thread
selection. Key/settings changes hold the earlier queue; they do not redirect it
to new settings. Cancel releases its exact unstarted reservation. Coordinator
recovery holds pending work and never launches inference. Explicit Stop
interrupts the original worker and transport; unconfirmed effects remain unknown.

API leases block session deletion while admission/transport is active or unknown.
Disconnect/delete cannot remove held original credentials. After confirmed
release, the existing name/scope/revision-confirmed session deletion removes
private histories and API provenance while preserving lifetime numeric totals.
Provider retirement keeps its original public revision/receipt references; it
does not convert or remove another provider's conversations. Source/aggregate
SQLite restore and repeated native scans reuse the same numeric receipt keys.
Normal API runs never invent GOAL time; Goal remains explicitly unavailable.

## Qualified evidence and remaining work

Focused owned Python cases cover explicit/partial/missing usage, native default
zeros, private origin bindings, unchanged subscription identities, real SQLite
source/aggregate restore, queue/key rotation, unknown admission and provider/
session deletion with retained lifetime totals. Node cases validate only reported
counter fields and bounded SSE/UTF8 observations. Actual pinned Codex0.163.0
workers in empty network namespaces cover project/skill, generic HTTPS and
OpenRouter, local Responses/Chat, original function receipts and same-thread
resume, explicit write denial, unsupported image capture before a broker call,
missing usage and Stop. Positive four-response cases report exactly64 tokens,
including8 cached input tokens and0 reported reasoning tokens, with cache-write
unknown. Missing usage remains entirely unknown. These are protocol receivers;
no real model inference, model installation or user VM/build/deploy action occurs.

Browser1440/320 provider/session/capability evidence from0.8.14–16 remains valid
for unchanged frontend components. This release changes backend accounting and
private protocol observations. Build/TypeScript/lint and immutable installation/
original-data verification remain required. Evidence:
`Research/R4OS/Roadmap-Implementation/0.8.17/` in the workspace.

**Subversion0.8.17 remains open.** Its available session/rights and usage work can
be recorded separately. Automatic60-second/five-attempt retries and their shared
lifecycle/final acceptance depend on the still-open0.8.10 controller. No retry
was enabled, no past run resumed and no Goal/extra capability inferred from API
reachability. See [Provider-Retries.md](Provider-Retries.md). Later independent
provider work may proceed while these specific items remain explicitly open.
