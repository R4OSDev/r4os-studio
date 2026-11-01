## Desktop icons and project publication (0.8.84)

Desktop icons already use manifest ICON (first resource, type1/index0) and a
R4LNK in C:\R4OS\DESKTOP with ICON=INTERNAL, as shipped by Notepad. No window-icon
setter is required. New profile18 sessions can explicitly deploy a GUI R4X with
desktopShortcut=true; existing conversations retain their schema and can use
Deploy to desktop on their completed development cards. Current run guidance
explains both paths. Publication owns only the project's derived link and chosen
deployment; normal test deployments preserve it. Foreign/edited links and unknown
results are protected. Never substitute global Desktop input or system-path shell
writes. Link readback, embedded icon and visible guest consumption are separate;
publication does not launch the app or complete a visual acceptance. Details and
exact source pins: Desktop-Shortcuts.md. Taskbar/window icons remain separate.

## Host-only tests and cc (0.8.9)

Tool terminals expose the existing validated public host `cc` driver with one
read-only private alternative and `/host-tools/cc` in PATH. No whole host `/etc`
or alternatives directory is mounted. Invalid/missing/foreign alternatives
produce `Host C linker unavailable` and exit127; ordinary non-compiler tools
continue to work. This does not change native R4X compiler or linker selection.
Use the project's bound Rust for a host-only `rustc --test`; do not rewrite test
scripts, Cargo.lock, project pins or global defaults as a linker workaround.
GCC14.2.0 is the checked driver on this host, not a required global version.

# Project environment qualification (0.8.3 / 0.8.73)

Host builds, guest facilities and Studio adapters have separate capabilities.
Runtime guidance includes this project's actual language/role and immutable
SDK/Contract/compiler pins. Older deployments keep their original build pins and
VM/boot binding. The private helper pins below never replace project pins,
application sources, saved prompts or existing native conversations.

## Own window controls

Qualified immutable sources:

| Component | Version / revision | Source |
| --- | --- | --- |
| Private helper SDK | 0.64.127 / fbb5041487441473612d04d3166bcfa21f3d555f | r4os/desktop_actions.zig, desktop_evidence.zig, README.md |
| Matching Contract | 0.64.68 / 4c96b21df75662ca6a3af3c8ee332c342e2db185 | Generated/SDK/Zig/abi_generated.zig and abi.zig |
| Full guest | 0.88.107 / Kernel0.1.452 | verified image and R4OS-SOURCES-0.88.107.json |
| WINSVC | 0.1.31 / a670557e352e1b574b08494756b58b86cb80ca59 | desktop_actions, desktop_evidence, main.zig |
| Desktop | 0.1.198 / 0a5b341ce3253cb073d3760b7ad0dea5732cf84b | src/rust/hosted/actions.rs, windows/service_mirror.rs |
| DESKRUN | 0.1.3 / 5d5fa5b001a649bd4245d4ad29eef9b9839c8a65 | original launch scope and controller grant |

New project sessions use tool profile16. Earlier conversations keep their exact
original declarations. studio_control_app_window requires its own enabled
session permission, an active own job and a new window-control-v1 deployment.
Request windowControl=true on studio_run_project only when that run needs window
actions. Ordinary starts keep their previous argument budget.

DESKRUN delegates that original child to the exact helper process generation.
Original request, 192-bit broker epoch, grant, controller, Desktop, app generation
and window incarnation stay bound. Resize uses client dimensions and preserves
the observed position. Minimize/restore use native WM commands. No registry write,
global input workaround or arbitrary PID/window is accepted. The controller flag
consumes the same112-byte SSH command budget. Overlong commands fail before app
start; never truncate arguments or launch a replacement app automatically.

The host saves the complete native request, original operation and deadline
before one submission. Read action=status for its original operationId after
uncertainty. Applied is an immutable native receipt; Current is a separate live
view. frameReady requires the actual composed view and a fresh app frame when
visible. Missing/pending frames are not passing visual tests. Applied view changes
invalidate older screenshot input references; capture again before input.
Unknown effects remain protected and are not replayed.

A separate Full0.88.107 KVM guest qualifies real resize/minimize/restore of one
C GUI process/window, actual pixels and fresh native frame receipts, preserved
app state and a subsequent consumed click. Tampered targets, discarded native
restore reply, actual GUI-slot reuse and an ended controller retain protection.
This is not an outside-client drag test. Guests/deployments without a confirmed
grant stay unsupported; original jobs/helpers are not migrated.

## C GUI, capture and output

SDK127 Shared/C/include/r4os/app_gui.h provides typed focus-gained/lost and
font-changed raw events/messages, named R4_GUI_WINDOW_FLAG_* flags and native
pointer identity/capture/status/release with window-incarnation binding. Use the
selected project's own facade/generated header. GUI flags and WindowService
registry flags have different meanings; never copy numeric values between them
or invent local ABI constants for an older SDK.

Applications can use their selected SDK's actual capture contract. Studio's
bounded gesture tool still stays within the own client and never holds a press
across calls. Native availability alone does not qualify an outside-client Studio
drag or global input.

New profile17 sessions and drag-interrupt-v1 deployments can include Escape or
an originally delegated resize/minimize before the final up in the same bounded
gesture. Older profiles retain their input schemas. Window interrupts additionally
need the original run's windowControl=true and Control app window permission.
The original native request/operation is persisted before input and never replayed.
The guest records apply while release is still pending; actual held app state,
Escape/focus consumption and a composed frame still need their own observations.
Restore separately after inspecting the original result. Full0.88.107 native
host input is bound to the registered Desktop, so outside-client routing is still
unsupported by this helper. See Drag-Interrupts.md.

Desktop owns lifecycle and consuming reap. New desktopEvidence-v1 helpers use
the original epoch and acknowledged WINSVC lease to retain exact exit and output
after Desktop cleanup. Native flags distinguish complete empty output, truncation
and incomplete output. GUI writes can become observable through retained terminal
completion rather than a live console: empty running output does not prove the
app wrote nothing. Process end, cleanup, exit, complete text and visual criteria
stay separate. Missing/stale leases and older helpers get no invented evidence.
See the0.8.72 README section.

## Provider and language boundaries

Historical Solitaire/Full0.87.14 failures for long Exchange staging names are
provider/volume observations, not a universal8.3 SDK rule. Studio's short package
and control filenames are its transport layout. Preserve app names and pins; use
rules documented or exposed by the actual selected provider.

Host Rust builds do not qualify a compiler in the guest. SDK127 delivery
explicitly excludes native Rust-compilation qualification, and this feature adds
no Studio guest Rust-build adapter. Inspect actual release capabilities instead
of repeating an old SDK92 limitation as a current global rule. POST/SSE,
cancellation/request size, TCP deadlines/PeerClosed and Unicode likewise follow
the selected SDK and running guest. A Studio model provider does not extend guest
APIs. Preserve codepoints and inspect current sources/errors; historical Nexus
findings do not prove a limitation persists after an upstream update.
