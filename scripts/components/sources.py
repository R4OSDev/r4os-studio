"""Fixed official source adapters; callers cannot supply repositories or download URLs."""
from packages import ADAPTER as PACKAGES
from tooling import Codex, Qemu, Zig
from images import Releases
from r4upack import R4UPack
from rust import Rust
from sdk_releases import SdkReleases

ADAPTERS = {kind: PACKAGES for kind in ('sdk', 'contract', 'libraries')}
ADAPTERS.update(zig=Zig(), qemu=Qemu(), codex=Codex())
ADAPTERS['r4os'] = Releases()
ADAPTERS['rust'] = Rust()
ADAPTERS['sdk'] = SdkReleases()

ADAPTERS['r4upack'] = R4UPack()
