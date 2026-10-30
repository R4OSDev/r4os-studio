# Roadmap presentation

## Main version and navigation (0.8.35)

The shared page header now reads **Project name Roadmap**, with Refresh in the
same header. The repeated panel title and shared-session explanatory line are
removed. This changes presentation; roadmap sharing, selection and permissions
keep their existing contracts.

The selected main version has its own card, separate from Subversions. Its upper
area splits equally: the saved number/title and task/acceptance progress on the
left; saved status/Current and export space above number/title/status fields on
the right. The export slot immediately precedes saved status; its existing text
button/download details remain until 0.8.36. Below this grid, Vision and Version
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

Direct export and the Subversions presentation follow in 0.8.36 and 0.8.37.
