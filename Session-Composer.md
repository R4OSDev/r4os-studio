# Session composer

## Goal and model layout (0.8.38)

The Goal card uses equal outer columns around the controls, so Play/Pause/Stop
remain centered independently of the caption or status width. GOAL is larger on
the left; the actual status and existing execution clock are stacked at equal
font size on the right. The second row centers the objective, retaining its
full tooltip and accessible editor name. Long text/status/time remain contained.
No Goal eligibility, clock measurement, request recovery or editor/save logic
changes. The STOP color adjustment remains the separate 0.8.44 task.

Account/Model/Reasoning/Fast Mode share their own matching frame with padding
and responsive wrapping. The context gauge remains immediately right of Model
inside that frame; attachment/send controls remain outside. Model choice,
provider binding, save/recovery and disabled conditions are unchanged.

Actual read-only Main-session inspection at 1440/320 px confirmed zero-pixel
control-center deviation, equal 11 px status/clock text, 18 px GOAL caption,
centered objective, matching frame and no horizontal overflow. Long values
were inspected through temporary DOM changes only. No Goal or model actions,
new tests/fixtures or inference were needed. Build/TypeScript/lint passed.

## Stored upload inventory (0.8.39)

The separate Stored uploads text row is removed. A storage icon appears directly
before Attach files only when the current owner/session listing confirms files
or cleanup-pending entries, including already sent files. Confirmed empty data
leaves no placeholder. Unknown reads show an inline error and explicit retry,
without claiming the session is empty.

The existing metadata-only listing is read once on session entry and refreshed
after confirmed upload/reconciliation, acceptance and deletion events. Short
notifications coalesce; superseded reads are aborted and also checked by sequence
and scope. No file contents or query per render is needed. The existing storage
dialog retains quota, Sent/Unused/Cleanup pending and deletion rules. After the
last file disappears, closing the dialog focuses the remaining Attach button.
The paperclip SVG moves 2.5 px right inside its unchanged button/hit area.

Focused checks extended the existing controlled SessionPanel preview for the
new listing/focus logic: empty inventory, confirmed upload, sent and cleanup-only
files, last deletion/focus, stale owner responses and failed read/retry. The UI
was inspected at 1440/320 px. The existing binary attachment API/receipt checks,
build/TypeScript and lint passed. No user uploads were created or deleted.
