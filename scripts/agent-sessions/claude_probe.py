"""One fixed, bounded SDK/CLI metadata probe with no credentials."""
import asyncio
import json
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from workspace_context import Workspace
import signal
import tempfile

from api_provider_store import private
from claude_runtime import installed
from session_store import identity
from store import ProjectFault


async def probe(providers,state,request_id):
    request_id=identity(request_id);runtime=await asyncio.to_thread(installed,providers)
    # The existing agents directory deliberately has its own, older mode.
    # Give this new facility its own private root; never chmod user run storage.
    state=Path(state).absolute()/'ClaudeControl';private(state,directory=True,create=True)
    with tempfile.TemporaryDirectory(prefix='claude-control-',dir=state) as temporary:
        root=Path(temporary)
        for name in ('Home','Config'):(root/name).mkdir(mode=0o700)
        source=Path(__file__).resolve().parent
        from claude_auth import auth_environment
        args=Workspace(root).command(['/usr/bin/node', str(source/'claude_control_probe.mjs'), request_id],
            environment=auth_environment(runtime, root))
        child=None
        try:
            child=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env={'PATH':'/usr/bin'},start_new_session=True)
            raw=await asyncio.wait_for(child.stdout.read(65537),20)
            if len(raw)>65536:raise ValueError()
            await asyncio.wait_for(child.wait(),3)
            if child.returncode:raise ValueError()
            value=json.loads(raw)
            if (set(value)!={'schema','nativeVersion','sdkVersion','advertisedModels','accountFieldNames','subscriptionVerified',
                    'promptMessagesSubmitted','toolsAuthorized','modelTurnsQualified'} or type(value['schema']) is not int or value['schema']!=1
                    or value['nativeVersion']!=runtime['version'] or value['sdkVersion']!=runtime['sdkVersion']
                    or type(value['advertisedModels']) is not int or not 0<=value['advertisedModels']<=256
                    or not isinstance(value['accountFieldNames'],list) or len(value['accountFieldNames'])>6
                    or any(v not in ('tokenSource','apiProvider','apiKeySource','email','organization','subscriptionType') for v in value['accountFieldNames'])
                    or value['subscriptionVerified'] is not False or value['promptMessagesSubmitted']!=0
                    or value['toolsAuthorized'] is not False or value['modelTurnsQualified'] is not False):raise ValueError()
            return value|{'requestId':request_id,'runtimeProfileId':runtime['id'],'filesystemIsolated':False,'networkIsolated':False}
        except asyncio.CancelledError:raise
        except (OSError,ValueError,TypeError,asyncio.TimeoutError):
            raise ProjectFault('The original Claude metadata probe could not be confirmed. No model prompt or login was submitted.',503) from None
        finally:
            if child and child.returncode is None:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                await child.wait()
