"""Load only the private relay nonce into the native model process environment."""
import os
from pathlib import Path
import re
import stat
import sys

path=Path('/api/relay.key');value=path.lstat()
if (not stat.S_ISREG(value.st_mode) or value.st_uid!=os.geteuid() or stat.S_IMODE(value.st_mode)!=0o600
        or value.st_nlink!=1 or value.st_size!=64):raise SystemExit('The private model transport is unavailable.')
token=path.read_text()
if not re.fullmatch('[a-f0-9]{64}',token):raise SystemExit('The private model transport is unavailable.')
environment=dict(os.environ);environment['STUDIO_API_RELAY_TOKEN']=token
os.execve('/bin/codex',['/bin/codex',*sys.argv[1:]],environment)
