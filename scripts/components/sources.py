"""Fixed official source adapters; callers cannot supply repositories or download URLs."""
from packages import ADAPTER as PACKAGES

ADAPTERS = {kind: PACKAGES for kind in ('sdk', 'contract', 'libraries')}
