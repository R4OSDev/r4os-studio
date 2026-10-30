# Local project opening (0.8.30)

Choosing a project now enables its navigation on the next React render. Local
session, editor, roadmap and board content waits only for its own data, while
the existing GitHub remote check runs in the background. Session lists load
only in Sessions and retain at most eight owner-bound lists for return visits;
the retained list is revalidated and cannot supply a current activity signal.
The independent project folder activity endpoint remains authoritative.

An opening check is shared while pending for the same project and complete
repository/branch/binding identity. CSRF rotation and internal view changes are
not new openings. The unprivileged Git coordinator joins an already active
check only when its frozen binding fingerprint matches. Clients poll the
returned original job ID, including when it differs from the new request ID.
No alias job is written, concurrency limits stay in force and unknown jobs are
not treated as running/completed. The worker checks binding revision again.
Existing workers and immutable accepted inputs remain untouched; idle adoption
loads new coordinator code through the ordinary release update.

Leaving a view aborts its binding read and ignores old results, but does not
cancel a shared original Git job. Only pending promises are cached (at most
eight); completed checks are not reused as a new opening's fresh remote state.
A returned status must be fresh and match the repository identity, and a new
local binding read must still match before presenting Update/Ignore. Failed,
unavailable or changed-binding results stay explicit, with Refresh, while
local work remains usable. Selecting another project cannot show an old prompt.

The background result never gates or remounts the local content. Composer drafts
and open editor state remain intact. Update/Ignore remains an explicit choice;
Update checks current form/run conditions and binding, then uses the existing
prepare/validate/apply pull contract with current workspace, snapshot, idle,
pin and revision checks. Editor drafts are checked before preparation and again
before apply. Ignore changes only this opening's display decision.

Focused qualification on this host used the actual ProjectsWorkspace and
SessionPanel with isolated, controlled API responses and a 2300 ms remote check.
At 1440/320 px, first navigation took 24/13 ms, first local session list 88/84 ms
and warm return 23/25 ms. With an artificial 650 ms local refresh, the cached
warm list stayed below 500 ms; first-time uncached lists correctly waited for
their own data. These are controlled browser measurements, not a production
network or GitHub latency promise. Fast A/B/A, concurrent consumers/auth rotation,
draft/mount preservation, dirty editor pull refusal, failed check, changed branch,
manual Refresh and no unrelated roadmap/board loading passed.

One isolated coordinator test covers original-job joining, no duplicate worker
or alias receipt, changed binding, unknown state and worker admission. The
protected HTTP route case covers the typed check field and existing auth/CSRF/
origin boundaries. Build, frontend/backend TypeScript, ESLint and Python AST
checks complete the release validation. No user source, native history, project
pin, provider credential, agent run or VM was changed by qualification.

Evidence: `Research/R4OS/Roadmap-Implementation/0.8.30/` in the development
workspace. Earlier analysis and host GET timings are retained in
`Research/R4OS/Projects/Switch-Performance-Planning/`.
