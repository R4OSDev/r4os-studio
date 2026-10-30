# Roadmap presentation

## Main version and navigation (0.8.35)

The shared page header now reads **Project name Roadmap**, with Refresh in the
same header. The repeated panel title and shared-session explanatory line are
removed. This changes presentation; roadmap sharing, selection and permissions
keep their existing contracts.

The selected main version has its own card, separate from Subversions. Its upper
area splits equally: the saved number/title and task/acceptance progress on the
left; saved status/Current and export space above number/title/status fields on
the right. The export slot immediately precedes saved status; it now contains the direct download icon from 0.8.36. Below this grid, Vision and Version
notes span the whole card and start closed. The layout stacks when the available
card area is narrow. Subversions follow the card; Cleanup history stays last.

Metadata, vision and notes still use one form and one draft. Folding keeps its
textarea mounted, so local text and native keyboard/focus behavior survive.
Save/Cancel, expected revision, retained original request, validation, conflict
and busy behavior are unchanged. The saved status badge remains distinct from
the editable draft status. Make current/original selection stays explicit.
Background revision observations show the existing refresh notice and do not
remount or replace the draft. Other entry/create dialogs keep their forms.

Version entries in column three now have two lines: number and one-line title,
then saved status/Current. Long titles use ellipsis, with full text in the
tooltip and accessible button name. Version order, selection, pagination,
Overview/New Version and dirty/busy guards retain their existing behavior.

Qualification used the actual frontend and real R4Craft roadmap over a temporary
local preview that blocks non-GET API requests. No synthetic roadmap dataset,
new unit test or browser fixture was added. At 1440 px the two columns measured
344.47/344.48 px; at 320 px they stacked without horizontal overflow. Native
disclosures started closed. A long local Vision edit survived folding and a
normal background revision check; unsaved text disabled export. Cancel restored
the original text and default folds. Version notes also retained a local edit
across folding and Cancel; native Enter activation and summary focus were
confirmed. Server roadmap revision/current binding
were identical before and after. Temporary DOM-only long-label inspection
confirmed wrapping/ellipsis without changing stored project/version names.
The existing submission/revision/original-request function is byte-identical;
source and existing guards were reviewed. Build, frontend/backend TypeScript
and ESLint complete the release checks.

Evidence: `Research/R4OS/Roadmap-Implementation/0.8.35/` in the development
workspace. The temporary preview deliberately rejects the usual background Git
check POST; this preview-only notice is not an application remote-check failure.

The Subversions presentation follows in 0.8.37.

## Direct export (0.8.36)

A compact download icon sits immediately before saved status. Its English name
and tooltip describe preparation, resuming an original request or downloading
an already confirmed snapshot again. Dirty/busy guards, keyboard focus and
reduced motion remain available. Successful preparation immediately hands the
existing protected content URL to the browser; no result link or Export details
appears. Download initiation does not claim a completed file save.

Session storage retains the original request and confirmed metadata for each
project/version. Requests from the old button remain recoverable. Temporary or
unknown failures retry the same input/ID; a confirmed snapshot is reused for the
same saved revision. A synchronous latch coalesces double clicks. An unmounted
selection cannot initiate a late download or replace a newer retained request.
The backend API, immutable UTF-8 snapshot, filename and SHA/byte validation are
unchanged; cleanup-history archive links keep their separate behavior.

Qualification used the actual control with an isolated real backend and native
browser downloads at 1440/320 px. Download bytes/SHA/filename and full Unicode
hierarchy matched server metadata. Dirty/double-click, historical selection, a
reply lost after server preparation, same-ID recovery and selection changes
were checked. The existing project-roadmap API/export test, build/TypeScript
and lint passed. No user roadmap, session or VM was changed.

## Subversion cards (0.8.37)

Subversions form a separate list of evenly spaced cards. Native disclosure
headers show a chevron, number/title, textual saved status and separate confirmed
task/acceptance totals, including discarded counts. Titles wrap fully. Existing
project/subversion expansion storage and order are retained. Reorder buttons
have a separate footer outside the clickable summary.

Expanded cards separate description/notes, entry actions, Tasks and Acceptance
items. Open/Done/Discarded groups keep visible text labels; counts on incomplete
pages say loaded. Descriptions/notes remain focusable scroll regions with their
full text. Add/Edit/Append/Replace/Mark done/Reopen/Delete, confirmation, retained
original requests and pagination keep their previous paths. Cleanup history
stays the final independent block. This release changes no stored statuses,
order, notes, IDs, permissions or agent instructions.

The actual frontend was inspected against read-only real R4Craft data at
1440/320 px: native keyboard disclosure, editor/note routing without saves,
header progress/status, complete description access, reorder placement and
pagination. A temporary DOM-only long title caused no horizontal overflow.
Existing mutation/recovery code is byte-identical. Build/TypeScript/lint passed;
no new tests or fixtures were added for styling. Evidence is in the development
workspace under Research/R4OS/Roadmap-Implementation/0.8.37/.
