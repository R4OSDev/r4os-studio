"""Fixed native metadata entry using only the original provider auth home."""
from pathlib import Path

from claude_auth import command
from api_provider_store import private
from session_store import identity


def limits_command(runtime,root,request_id):
    private(root/'Config/projects',directory=True,create=True)
    args=command(runtime,root,'status');args=args[:args.index('--')]
    blocked=args.index('CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC')
    assert args[blocked-1]=='--setenv'
    del args[blocked-1:blocked+2]
    source=Path(__file__).resolve().parent
    # Auth may update its own native files; original conversation directories
    # are neither exposed nor scanned. No model input is supplied.
    args+=['--tmpfs','/config/projects','--ro-bind',str(Path(runtime['sdk']).parent),'/runtime/sdk',
        '--ro-bind',str(source/'claude_engine.mjs'),'/runtime/claude_engine.mjs',
        '--ro-bind',str(source/'claude_limits_probe.mjs'),'/runtime/claude_limits_probe.mjs',
        '--','/usr/bin/node','/runtime/claude_limits_probe.mjs',identity(request_id)]
    return args
