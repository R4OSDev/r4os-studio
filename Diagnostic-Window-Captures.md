# Diagnostic Desktop captures (0.8.41)

Process/window confirmation and the native DESKRUN content marker are separate.
The existing adapter already reconciles only the original STATUS request within
its bounded retention/deadline. A window-phase receipt with errorlevel 9 and
content 0 therefore stays desktop_content_unconfirmed; no artificial ready flag,
new launch or endless polling is introduced.

Capture may now produce a diagnostic image when the original running job,
project revision, VM lease/image/boot, DESKRUN process generation and window slot
match a visible, focused own window with valid bounded geometry. Window metadata
is compared before and after capture and the observation must finish within
30 seconds. Missing/stale/foreign identities remain rejected. Capture never
launches, focuses, reaps or stops anything.

Such immutable evidence carries diagnosticOnly/contentUnconfirmed and explicitly
disables input/completion references. Frame validation rejects it for all GUI
input and completion; visual assessment also rejects diagnostic frames. Normal
ready captures retain their existing path. Job details and the screenshot
gallery label diagnostic images, while readiness separately shows process,
window and missing content evidence and the bounded STATUS retention state.
Native rendering/retention issues remain R4OS findings.

Three isolated cases plus existing frame/unknown-launch checks cover diagnostic
versus regular captures, no input/assessment/completion eligibility, wrong owner/
boot/process, changed geometry/focus and the existing STATUS deadline. Five
checks, Python AST, build/TypeScript and lint passed without a user VM capture,
new launch or replay of the old Nexus job. Evidence:
Research/R4OS/Roadmap-Implementation/0.8.41/ in the development workspace.
