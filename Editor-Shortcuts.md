# Owned-client editor shortcuts (0.9.6)

New `studio-tools-v20` conversations may send `kind=key`, `key=Ctrl+A` with a
recent focused own `frameId`. Omit repeat or use1. This queues the pinned SDK's
public `r4os.gui.Key.ctrl_a` codepoint0x01, handled as Select All by its TextField
and TextArea. It is one semantic GUI event: no physical Ctrl key is pressed,
held or released across calls. No release event is required and no modifier
state can remain held. This does not provide arbitrary modifier sequences or
clipboard access. Ctrl+Home and Ctrl+End have no qualified representation in the
reviewed public key contract and are explicitly unavailable.

The host checks the original run's frozen Send VM input permission, exact
process generation, original own window/frame, current focus and geometry.
It requires `editorShortcutVersion=1` from a newly deployed private helper,
`guiFrameBindingVersion=1` and repeat1 before submission. The guest rechecks its
own process/window binding and accepts ctrl_a only under this versioned request.
Existing deployments/worker pins are preserved. New helper source hashes change
under the same private SDK0.64.127/Contract0.64.68/Zig0.16.0 build pins.

The durable original input receipt records accepted/expected, semanticCodepoint,
heldModifiers=false and releaseRequired=false. Enqueue is not application
consumption or proof that all text is selected; inspect a new image/output and
then use normal editing. Lost or partial responses do not authorize replay.
Ordinary keys retain their repeat1..16 behavior, and older conversations retain
their exact declarations and key contract. Read-only options and session settings
explain the qualified allowlist and deployment requirement without granting rights.

Static checks and both private helper compilations are performed without tests,
fixtures, inference or application/VM runs. Positive text-field interaction
acceptance therefore remains open until actual native evidence is available.
