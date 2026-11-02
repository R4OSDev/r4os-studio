# Input after a rejected own-window action (0.9.3)

The native phase4/rejected/result-9 unsupported resize is a final rejection.
Previously the helper treated every submitted action without an applied frame
as pending, leaving input and future window preparation locked indefinitely.

The helper now keeps the immutable original operation outcome separately from
its current scope/view reply. Only a full match with the prepared request can
settle that operation: either confirmed applied/frame-ready, or an explicitly
negative terminal rejection. A current-view status read cannot erase that proof
or settle another operation. Every new command clears its own outcome first.
Pending, unknown, lost, mismatched and unqualified expired outcomes stay guarded.

After rejection, a scope read can qualify the current original window again.
The usual live process, focus, geometry, permissions and fresh-frame checks still
apply. Rejection never becomes applied success, old frames are not reused and
the resize is not repeated. The host receipt exposes terminalRejected/pending
and explains the next fresh-frame requirement.

This is a compatible behavior correction in window-control-v1. Existing helper
bytes and active worker pins remain untouched; a new explicitly requested
deployment uses the corrected content-addressed helper. App SDK/Contract pins
and native ABI are unchanged (private SDK0.64.127 / Contract0.64.68).

Qualification uses source/contract inspection, pinned helper compilation and
Studio static checks. No tests or application/VM runs are performed; actual
native rejected-resize/input acceptance remains pending runtime evidence.
