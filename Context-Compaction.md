# Studio context compaction

Studio prepares the complete next model request before deciding whether to
summarize. The planning threshold and target sit below the effective input
limit. The input limit still uses the frozen global and session policy and the
selected model's output reserve.

For new direct runs, an ordinary VM screenshot can become an original-result
reference when a confirmed request contained its pixels, the model used that
frame for an input action with a settled result, and a later capture replaced
the view. User attachments, historical image reads and captures with an analysis
question remain available. The original-result reader can retrieve the exact
archived image. The Context overlay shows the request body that was actually sent.

Direct OpenAI image profiles are scoped to documented model, endpoint and detail
combinations. The 32-pixel patch estimate applies to `gpt-4.1-mini-2025-04-14`
and `gpt-5.2` images that fit their documented sizing bounds. Other image inputs
use the conservative raster estimate. The overlay shows which estimate was used.
[OpenAI image input rules](https://developers.openai.com/api/docs/guides/images-vision)

Local summary requests use selected history, the current objective and original
references. Usage attribution stays in the request and conversation archives.
The summary has its own prompt, output target and 90-second timeout. A provider
output cap is sent through the public OpenAI Responses contract. A lower
reasoning setting is used only when the route and model support it.
[Responses request fields](https://developers.openai.com/api/reference/resources/responses/methods/create)

Studio commits a checkpoint when the confirmed summary reduces the complete
continuation and the original history head still matches. A preparation can use
up to three steps within its 180-second deadline. Context shows elapsed time,
committed steps, image counts and estimated input before and after each step.
Provider-reported usage remains available for the original request.

## Signed Messages history

Studio preserves the active Messages history for Claude-compatible connections.
The wire guard compares the system, tool declarations and messages before the
latest replayed signed block with its bound original request. A changed or
unavailable prefix stops dispatch. Local compaction leaves signed history and
open tool groups intact. Anthropic documents the same prefix requirement for
preserved thinking. [Anthropic preserved thinking](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking)

## Native compaction qualification

Public OpenAI Responses documents a standalone compaction request and a
compacted response with its own usage. The entire returned window is the
canonical input to the next request. Studio would need a binding for the actual
account, route and model, a verified continuation, enforceable input limits,
confirmed interruption behavior and a measured benefit before enabling it.
[OpenAI compaction guide](https://developers.openai.com/api/docs/guides/compaction)
[OpenAI compact endpoint](https://developers.openai.com/api/reference/resources/responses/methods/compact)

The Codex 0.163.0 source implements a separate typed trigger in its own client and
provider capability selection. That implementation is evidence about Codex.
Studio has no verified native compaction contract for its subscription
connection, public API account or other connectors. Direct Studio requests use
the local checkpoint path. New Responses runs stop if an unqualified native
compaction item appears in their input or output. The original journal retains
the received events.
