# Native desktop link activation qualification (0.9.5)

Publication, visible icon consumption, direct application launch and actual
activation through a desktop link are distinct facts. Studio's existing desktop
publication and normal own-process runner remain usable. Native own-link
activation is unavailable, exposed as `desktopLinkActivation.available=false`,
`reasonCode=native_link_activation_unqualified`. No new action is admitted.

The reviewed public SDK0.64.127 and Contract0.64.68 provide own-launch Desktop
actions and evidence, but no qualified link activation operation. The pinned
Desktop0.1.198 source resolves R4LNK into its shell `Item` during folder loading.
`shell/launch.rs` `Associations.item()` turns that resolved item into `Launch`.
`runtime/desktop_launch.rs` admits external launch messages as program paths,
arguments and policy. `hosted/launch_request.rs` likewise constructs a program
launch; it is not a link-activation receipt. Supplying the resolved APP.R4X to
these paths cannot prove that Desktop activated the original link.

A future native contract must accept one project-owned link identity and a
durable caller correlation before launch; validate exact link bytes and resolved
target; bind the Desktop/VM service instance and resulting process generation;
retain an idempotent original admission/result that can be read after lost SSH
ACKs without another start. Startup, readiness, end and cleanup stay separate.
Studio must recheck its publication receipt and exact verified deployment before
admission. Foreign/changed links and uncertain publications remain blocked.

Until that native contract is available and qualified, the activation adapter,
new activation tool and positive link-start acceptance remain open. Studio adds
no arbitrary paths, Desktop input, shell commands or expanded permissions. It
does not pretend that resolving the link then directly launching the target is
the requested behavior. Installation, metadata reads and publication never
start the app automatically.

Reviewed immutable source revisions:

- Desktop: `0a5b341ce3253cb073d3760b7ad0dea5732cf84b`.
- SDK: `fbb5041487441473612d04d3166bcfa21f3d555f`.
- Contract: `4c96b21df75662ca6a3af3c8ee332c342e2db185`.

Exact source URLs and SHA256s are retained in the workspace research evidence.
No tests, inference, guest commands, application launches or VM actions were
used for this source qualification. Existing deployments/pins/workers and old
tool declarations are unchanged.
