"""Fixed official source adapters; callers cannot supply repositories or download URLs."""
from tooling import Codex, Qemu
from images import Releases
from r4upack import R4UPack
from sdk_releases import SdkReleases

ADAPTERS = {'qemu': Qemu(), 'codex': Codex()}
ADAPTERS['r4os'] = Releases()
ADAPTERS['sdk'] = SdkReleases()

ADAPTERS['r4upack'] = R4UPack()
