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
