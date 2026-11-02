# Original development job references

Since 0.9.4, new `studio-tools-v19` conversations can recover an original
development job after a lost or truncated tool presentation. Existing threads
retain their exact declarations. No job, native process or session is replayed.

`studio_read_development_job({"lookup":{}})` returns small references for this
project session only. Pages contain at most 25 entries (10 by default) and are
bounded to approximately 8 KiB. Continue with `lookup.before=nextBefore` while
`hasMore`. Use a returned `id` as `jobId` in an ordinary read for current evidence.
The index omits settings, arguments, credentials, target paths and detailed logs.

An exact lookup can use `lookup.requestId`, the original Studio request UUID,
or both `lookup.originRunId` and `lookup.toolCallId`. The latter verifies the
original session/run/admission-tool binding and derives the same request UUID
used at admission. This UUID is not a native DESKRUN request key. The coordinator
verifies the active worker identity and frozen read permission; callers cannot
choose another agent session. Browser reads use the authenticated project API
`GET /api/projects/:id/development/sessions/:sessionId/jobs` with the same bounded
query fields and no-store caching.

Admission persists the request/job binding before returning details. Pending
session items also retain it; native results put a small `developmentReference`
before longer output. A response error remains `request_error` or `unknown`:
neither means the original effect was rejected or safe to repeat. An empty lookup
does not attest native non-admission. Missing exit, output and cleanup evidence
remain distinct and unknown.

On the next authorized run, older conversations receive up to six original own
job references as read-only runtime context. They use their existing `jobId`
argument, not the v19 lookup schema. Reference capture is optional and cannot
block a new run when unavailable. Already frozen or queued captures remain
unchanged, including captures without a reference index. This release starts
no conversation, job or VM and does not replace old workers.

The host updater requires the explicit, hash-checked local maintenance script
`scripts/agent-sessions/install-job-lookup-support.py` before installing the first
v19 release. Existing v18 compatibility and rollback identities remain intact;
the normal release updater performs installation afterward.
