# Session context measurements (0.8.24)

Session reads and the existing authenticated event stream expose a small
`context` snapshot, shared by project and skill sessions. Reading it makes no
model request, scans no transcript and changes no user data. Old workers and
unqualified engines show unavailable or an explicitly stale earlier sample.

For the pinned native Codex 0.163.0, the source is
`thread/tokenUsage/updated.tokenUsage.last.totalTokens` divided by the same
notification's `modelContextWindow`. `total` is cumulative consumption and is
not used here. Cache/reasoning values already included in native totals are
not added again. This is the full reported context, without the native TUI's
separate 12,000-token user-controllable baseline adjustment. Nominal model
maximum and auto-compaction threshold are not reported as effective capacity.

The actual native start/resume response establishes model/provider provenance;
the selected model remains a separate field. Original owner/session, engine
pins, provider, thread, latest active worker and turn gate each measurement.
Replayed/foreign/earlier-worker events cannot replace a newer snapshot.
Repeated identical samples do not increment its local revision. The source
does not provide a server measurement timestamp: `reportedAt` records Studio's
receipt time, and `revision` is Studio's ordering, not an invented native ID.

Compaction invalidates the preceding sample until a later measured result.
Tokens may then decrease. Rerouting and provider/model/thread changes wait for
matching provenance and a new reported window; old tokens are never divided
by a newly selected catalog maximum. Confirmed Stop, Pause and new runs on the
same conversation preserve the last reported measurement. An unknown run or a
new worker without this protocol makes earlier data stale.

Known zero needs a positive reported capacity. Missing/invalid fields remain
unknown. The raw ratio is retained, including overflow; remaining tokens clamp
at zero and overflow is explicit. API/local/Claude context bases are currently
unqualified and remain unavailable. No quota, price, lifetime-statistics or
GOAL-time contract changes. Session deletion removes only its own snapshot.

The speedometer and accessible detail tooltip follow separately in 0.8.25.
