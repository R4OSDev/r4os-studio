"""Fixed native metadata entry using only the original provider auth home."""
from pathlib import Path

from claude_auth import command
from api_provider_store import private
from session_store import identity


def limits_command(runtime,root,request_id,catalog=False):
    if type(catalog) is not bool:raise ValueError('Invalid fixed metadata mode.')
    private(root/'Config/projects',directory=True,create=True)
    from claude_auth import auth_environment
    from workspace_context import Workspace
    source=Path(__file__).resolve().parent
    return Workspace(root).command(['/usr/bin/node', str(source / 'claude_limits_probe.mjs'), identity(request_id),
        *(['catalog'] if catalog else [])], environment=auth_environment(runtime, root))
