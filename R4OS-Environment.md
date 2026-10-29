# Project environment qualification (0.8.3)

Host compilation, native guest facilities and Studio test adapters are separate
capabilities. Workers include the current project's language, role, revision and
SDK/Contract/compiler pins in their runtime guidance. These are startup metadata;
an older deployed artifact keeps its original build pins and VM/boot binding.
No project pins, application files, saved prompts or native threads are changed.

## Own window actions: native prerequisite remains open

Qualified sources:

| Component | Version / immutable revision | Relevant source |
| --- | --- | --- |
| Private helper SDK | 0.64.66 / 41770f2c354e461a5663ad805b7b2955dab1d5a9 | r4os/program.zig |
| Private helper Contract | 0.64.41 / 95f762623e6ac2025e9a8aa781713c7c957629a8 | Generated/SDK/Zig/abi.zig and abi_generated.zig |
| Nexus SDK | 0.64.92 / 51ed03d813d9baeab630746f1d1bbc46c2d2a1e6 | r4os/window_mode.zig, Shared/C/include/r4os/app_gui.h, README.md |
| Nexus Contract | 0.64.45 / db155842d346a8aae0aadea73288105140c95af6 | API/ApiContract.json, Generated/SDK/C/include/r4os/abi_technical_generated.h |
| Public WINSVC implementation snapshot | f54855b1e5a82e2591999a6561adbaf98155b5a6 | src/main.zig: performAction, src/window_mode.zig |
| Public Desktop implementation snapshot | af339ec95950e6a077c6bbe0c0cc24fbd6e49c12 | src/app.zig: mirrorWindow*, sendWindowServiceOp |

The legacy WINSVC minimize/restore/update operations change a stored record.
Desktop mirrors its own window operations into this registry. An accepted
registry request does not attest applied Desktop geometry or a visible state
change. `gui_set_window_info(instance_id, info)` likewise does not establish a
generation-bound, externally authorized WM request with an application receipt.

The newer `WindowModeRequest` does have owner, Desktop and service generations,
window incarnation and request IDs. Its documented modes are **0 decorated** and
**1 borderless fullscreen**. It has no width/height/minimize/restore request.
The existence of this qualified mode path must not be generalized to the three
requested operations. The source snapshots above are qualification evidence,
not a claim that a particular running guest has those revisions installed.

Studio exposes no mutating own-window adapter until the required native contract
is established. Needed: generation-/window-bound resize/minimize/restore, native
Desktop authorization, idempotent original request identity, actual applied
state/geometry readback and explicit stale/unsupported/unknown outcomes. A new
adapter will also need an explicit session right and frame invalidation. No
global mouse/key workaround or changing registry metadata as a test substitute.
The positive action/foreign-target/response-loss guest acceptance remains open.

## C GUI, capture and output

The higher `app_gui.h` raw/message facade is not the complete technical ABI.
The generated technical C header already defines focus/font event values.
The public facade and window-flag access need separate qualification against the
selected source. `WindowService` flags and `GuiWindowFlag` have different meanings;
do not copy numeric values between them or add local ABI constants.

The observed R4DESK v17 table and local `gui.MouseCapture` state do not establish
native capture of Move/Up outside the client. Bounded own-client gestures0.8.2
do not test an outside drag. An actual capture/release contract and native proof
remain necessary. Similarly, Desktop process end, helper cleanup, native exit
status, complete output and a visual assertion remain independent evidence;
completion retention after Desktop reap and Rust `App.write` routing remain
unconfirmed as described in the0.8.1 README section.

## Storage and Nexus limits

The stored Solitaire observations on Full0.87.14 show long staging basenames
failing Exchange stream creation while checked short basenames succeeded.
This is a provider/volume observation, not a universal8.3 naming rule or a proven
kernel/FAT defect. Preserve app names and pins; qualify the target provider's
stream-create/replace rules separately from SDK path syntax.

SDK0.64.92 explicitly describes native R4CC as a C subset and native Zig/Rust
compilers as unavailable. Studio's host Rust app builds do not contradict that.
The Nexus HTTP POST/SSE,12-KiB request buffer, TCP server deadline and
PeerClosed/remaining-data concerns are native language/API questions. A model
provider integration does not extend a guest SDK. No reproduction of packet loss
or TLS failure is asserted by source review. A reported glyph issue still needs
localization to application data, fonts and rendering; preserved Unicode text
must not be replaced as a guessed fix. The canonical112-byte Desktop command
budget remains enforced; its advance display is separately planned in0.8.42.

This release implements guidance and qualification only. No new window mutation,
permission, native tool declaration, guest binary or pin migration is introduced.
