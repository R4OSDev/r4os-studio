"""Fixed official source adapters; callers cannot supply repositories or download URLs."""
from packages import ADAPTER as PACKAGES
from tooling import Codex, Qemu, Zig

ADAPTERS = {kind: PACKAGES for kind in ('sdk', 'contract', 'libraries')}
ADAPTERS.update(zig=Zig(), qemu=Qemu(), codex=Codex())
