# Context input limits (0.12.15–17)

**System → Settings → Context → Limit** holds the global switch and input
budget. The existing value is preserved; the default is On / 250,000 tokens.
Off keeps the saved number. Reset restores On / 250,000.

In project and skill session settings, **Context** offers:

| Mode | Behavior |
| --- | --- |
| Off | Use model limits without the additional user budget. |
| Global default | Follow the global switch; this is the default. |
| On | Enable the additional budget independently of the global switch. |

When enabled, an optional session value replaces the saved global number.
An empty field uses the global number, including when the global switch is Off
and the session is On. A stored session value is kept and ignored while Off.
Lower model limits always take precedence.

The resolved policy and global revision are frozen when an input is accepted.
Changing settings starts no work and does not alter running or queued inputs,
their original worker, or their recovery configuration.

The budget covers the complete serialized provider request: system/workspace
instructions, tool definitions, conversation, summaries, tool observations,
document text, cache markers, signed provider blocks and images. It also applies
to summary requests, the Vision helper and image generation/edit requests. A
helper inherits its parent session policy and also uses its own model limit.

Studio checks a conservative local estimate immediately before opening the
model connection. Text and structure are charged at one token per UTF-8 byte,
plus 1,024 tokens and 16 tokens per JSON value for framing. Base64 image bytes
are replaced by a reserve of at least 65,536 tokens per raster, increasing for
large dimensions. This intentionally admits less input than a typical tokenizer;
it is **not an exact provider token count**, billing count or a guarantee about
arbitrary compatible servers' hidden processing. No extra counting/model
requests or new tokenizer dependencies are introduced. The configured model
window retains at least 20% output headroom and any larger declared output
reservation. Off never removes the model ceiling.

Older safe history is summarized in bounded sections, and each summary input
must fit too. Current human input, original archives, paired tools and unresolved
observations are retained. If the irreducible input cannot fit, Studio stops
before sending; it neither silently truncates it nor repeats tools. Unknown media
cannot masquerade as zero input. The Context indicator separates confirmed
provider input usage from the next-input estimate and effective input limit;
cached input is not subtracted from context size.

Native legacy connections own their full request internally. An enabled Studio
limit is refused before new work rather than silently ignored. Review an
explicit conversion under Conversation to use Studio limits, or select Off to
continue with native model limits. Existing accepted native runs are preserved.
