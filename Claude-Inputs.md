# Native Claude inputs (0.8.55)

Claude receives the frozen Studio system prompt and project Agents.md through
the SDK's explicit custom system-prompt snapshot. A hash and byte count bind the
composed sources to the accepted run; changed sources fail before submission.
Studio's published skill catalog uses that same snapshot. Skill resources remain
readable only through the existing permitted Studio broker and frozen revision.
Native file discovery, plugins, skills, subagents and host MCP configuration do
not substitute for Studio's sources or permissions.

## Attachments

Send freezes the ordered attachment IDs, original sizes/hashes and provenance.
The private worker builds explicit native text/image content blocks from those
originals and rechecks them before opening the native process. The bridge mounts
one bounded readonly input file rather than putting image bytes in control
commands or public events. Images are sent as base64 image blocks, following the
official [SDK input contract](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode).
The exact installed SDK0.3.312 declaration `SDKUserMessage.message` confirms this
Messages-compatible content-array contract; vendor/runtime hashes stay unchanged.

Fresh authenticated model-catalog receipts qualify image delivery for native
fixed Claude wire IDs through `shared/claude-input-profile.json`. The native
ModelInfo does not report this capability: its independent sources are the
provider's published vision contract and Studio's qualified SDK content path.
The catalog attributes images to `studio-input-profile`, preserving the source
of native aliases/effort separately. A minimal real Pro account check recognized
actual image colors, consumed the attached document marker and read a published
skill through one permitted file call using `claude-haiku-5-5`; this does not
claim a real inference for every model or an independent entitlement/billing
check. Existing catalog receipts are not upgraded;
read the native model catalog again to obtain the new capability.

Accepted still formats are PNG/JPEG/WebP, using the existing decoder and original
files. Studio bounds Claude images to4 MiB each and8 MiB of image data per send;
the complete native content is bounded to12 MiB. Oversized selections remain
stored and cause a concrete draft/server refusal. These are Studio's adapter
limits, not a claim about the provider's maximum. Formats and base64 content
follow the official [vision contract](https://platform.claude.com/docs/en/build-with-claude/vision).
No image URLs, external downloads or Files API credential path are used.

UTF-8 documents and PDFs retain the common explicit extracted-text contract.
Each block carries its attachment ID, name, original hash, extraction mode,
available text length, excerpt offsets and any limitations. PDFs are text
extraction, with no implied inspection of embedded images or scanned pages.
Long documents require permitted Read attachment and Read file to continue
beyond the bounded excerpt. An unreadable or inaccessible document is refused,
not silently omitted. Attachment-only messages need no invented user text.

Screenshot tool results use the same qualified model capability. Delivery needs
the original Capture VM permission and session/project/job/evidence binding.
Unqualified models receive a notice that the stored capture does not establish
visual inspection. Capturing, presenting and native image inspection remain
distinct operations; the real image acceptance uses an owned generated test
image and does not claim a new VM screenshot qualification.

## Original acceptance and recovery

The native stdin echo must confirm both the original request/text identity and
an ordered semantic digest of every text block and actual image bytes. Only
after that receipt may Studio tool effects execute. Object-key order does not
affect the digest; block order and image changes do. Public frames and private
receipt metadata contain hashes/identities rather than another copy of images.

Queues retain this frozen content contract. A subsequent response may reuse the
already confirmed receipt without presenting a second content echo; it cannot
replace the original. Missing/mismatched input, changed files, permissions,
provider/account changes, Stop and Unknown retain the usual no-replay guards.
Host restore never submits new input. GOAL does not send unsent attachments.
Legacy text-only frozen runs preserve their original protocol and hashes.

The unchanged SDK/CLI was checked with the production worker, admission and file
broker against owned TLS replies for ordinary and queued document/image inputs.
The actual Pro-account check uses an isolated temporary project/session and
native history with the existing provider's native auth home, without copying
credentials. It submits one explicit input and performs one readonly skill
call. Native preference/cache writes are retained; credential file hashes,
existing Studio sessions/history, pins and VMs are preserved. This source-worker
check is distinct from the installed production HTTP text workflow proved in52.

Hosted web search, native subagents, image generation, Fast Mode and implicit
host plugins remain unavailable. This input contract grants no tool, billing,
quota, network, VM or GitHub authority. Each send still needs fresh native
subscription admission with paid extra usage disabled. Context size remains
unknown unless a separately qualified original source reports it.
