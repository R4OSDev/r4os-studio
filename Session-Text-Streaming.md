# Live assistant text (0.8.29)

New live assistant text in project and skill sessions advances in complete
Unicode graphemes, with a brief violet glow on the latest four characters.
The original items and deltas enter the canonical session state immediately;
only their browser presentation waits. Tool output, notices and user messages
keep their existing rendering.

The protected SSE endpoint adds an optional `delivery` field. Initial and
reconnected backlog is `replay` until the connection has observed an empty
event batch; only subsequent events are `live`. There is no database, cursor,
native-history or provider change. Missing provenance defaults to immediate
display, so older workers/servers cannot make saved history type again.

The existing sanitized CommonMark renderer parses each received chunk once.
Its authoritative text leaves feed a single active animation controller;
animation frames change Text nodes without reparsing Markdown or mounting a
node for every character. Code copy retains the full received, sanitized code.
HTML, unsafe URLs, OSC/ANSI sequences and unregistered images keep the existing
restrictions. Registered images render directly without repeated reads.

`Intl.Segmenter` preserves emoji, combining marks and cross-leaf graphemes.
The adaptive rate is 90–900 graphemes/second, capped at 64 per frame. A pending
burst over 400 graphemes, more than 128 leaves, text over 8192 characters or a
480 ms backlog flushes immediately. Corrections/non-prefix snapshots are
authoritative and display fully. The local writing-edge highlight fades for
140 ms and changes neither layout nor the semantic text.

History, replay, completion, tool boundaries, Stop/run end, disconnect,
backgrounding and unmount flush/cancel pending presentation. Reduced Motion or
missing animation APIs displays full text directly. Selection freezes the
rendered Markdown snapshot while canonical input continues; release or code
copy exposes the newest received snapshot. Pointer gestures flush pending
characters before selection. There is one accessible text representation with
`aria-live="off"`; existing follow/manual-scroll behavior remains independent.

Focused checks passed: the actual SessionPanel at 1440 and 320 px with controlled
live/replay events, grapheme-by-grapheme DOM samples, immediate canonical input,
corrections/duplicates, old history, tool/run/disconnect/hidden boundaries,
selection/code copy, sanitized Markdown/media, large bursts, Reduced Motion,
unsupported-API fallback, manual scrolling and project/skill scope changes.
Two SSE/backpressure groups and the existing transcript security test passed.
No model inference, user-session mutation or VM action was required.

Primary browser references:
[CSS Custom Highlight API](https://developer.mozilla.org/en-US/docs/Web/API/CSS_Custom_Highlight_API)
and [::highlight](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Selectors/::highlight).
Checks and screenshots: `Research/R4OS/Roadmap-Implementation/0.8.29/` in the
development workspace.
