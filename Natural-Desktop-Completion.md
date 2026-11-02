# Natural Desktop completion

The development worker now gives an unknown process observation up to five
seconds of status-only observation when its original acknowledged Desktop
evidence lease matches the launch request and exact process generation. This
covers a natural Escape/Q exit after Desktop removes the window, in addition
to the existing explicit check-completion wait. It never repeats Q, Close,
DESKRUN, evidence reservation or Goal Play.

The original token, request identity and process generation must match the
saved phase4 acknowledgement. Missing, damaged, foreign or unacknowledged
evidence does not qualify. An unresolved observation remains unknown after
the bounded wait. Native watchdog deadlines are unchanged.

`natural-end-observation.json` records the original request, target, status-only
mode, observation count and result. A genuine completion proceeds through
the existing independent exit-code, output, helper-cleanup and closed-receipt
path. A missing window alone never supplies an exit code or a successful test.

The two original saved incidents both contain acknowledged phase4 tokens and
matching process generations with `window_process_identity_unavailable`;
neither has a private `closed.json`. They remain historical unknowns until
their actual original completion and cleanup are reconciled. This change
does not rewrite their frozen workers, histories or tool receipts. Read-only
unknown-job semantics were already fixed in0.8.81.

Qualification uses source/receipt inspection and static Studio checks only;
no tests, new application/VM runs or model inference were performed. Real
native retention and delayed-completion acceptance remain dependent on actual
generation-bound runtime evidence.
