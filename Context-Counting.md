# Full input counting

New inputs accepted from 0.12.22 freeze context-policy schema 4 and the counting
profile alongside the resolved global/session limit. Existing accepted inputs,
queues and historical requests retain their original method. Limits remain input
tokens; the lower model ceiling and output reservation still apply.

The first profile counts Unicode codepoints in the complete prepared request,
including instructions, tools, history, checkpoints and protocol fields. Its
fallback uses characters / 3 per disjoint component, plus 1,024 framing tokens and
16 per message, and separate raster reserves. Base64 image pixels are excluded
from text counting. This is a local planning estimate, not provider usage or a
guarantee about server-internal tokenization. Unknown media is not assumed free.

The same frozen profile feeds planning, summary/media helpers and the final
pre-dispatch check. Required input that cannot fit before any consumed history
exists reports its system, tools and conversation amounts. It is not described
as an unresolved tool observation. Transport byte limits remain separate.

Original request metadata keeps the request hash, Unicode characters, method,
version, model binding, reserves and disjoint categories. Historical schema-3
UTF-8-byte/raster estimates remain unchanged. Inspection does not execute inputs.
