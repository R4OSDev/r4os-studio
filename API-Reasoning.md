# OpenRouter reasoning

## 0.9.36: metadata and selection

OpenRouter model facts preserve `mandatory`, `supported_efforts`,
`default_effort` and `default_enabled`. Missing effort options mean there is no
effort selector; null means all documented gateway levels. The gateway levels
include `max`. Mandatory reasoning excludes `none`. An empty selection is the
provider default and must not be sent as `none`.

Metadata refresh keeps explicit manual model facts. Matching current reasoning
metadata is retained separately and any mismatch is visible. **Apply latest
reasoning metadata** opens a draft with those facts and preserves a valid
explicit default. Save uses the regular catalog revision and original request
receipt. Its private journal retains the previous and replacement model facts.
No refresh or save performs inference or rewrites existing sessions or frozen
run snapshots.

New automatically imported Crouton Alpha metadata provides the documented
`max` default. An explicit valid `minimal` default remains `minimal`.
The model is still unavailable until the reasoning wire/history support is
implemented; model metadata alone is not a completed transport qualification.
GOAL availability follows the same effective adapter availability.

Official contract: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens

Studio uses the current configured Codex default for new sessions. No model
name or Codex version allowlist is added by this feature.
