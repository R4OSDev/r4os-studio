"""Fixed native SDK namespace; project tools never inherit this credential home."""
import json
import os
from pathlib import Path

from api_provider_store import private
from claude_auth import auth_home
from claude_auth_store import AuthStore
from claude_runtime import installed
from session_store import identity
from tool_catalog import specifications
from store import ProjectFault


def write_new(path,value,maximum=262144):
    data=json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()
    if len(data)>maximum:raise ProjectFault('The frozen Claude bridge configuration exceeds its bound.',409)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())


def prepare(worker,history,prepared,broker):
    """Called only by an admitted worker after verifying its frozen native lease."""
    runtime=installed(worker.manifest['providers']);config=worker.config
    frozen=prepared['runtime']
    if (config['engine'].get('kind')!='claude-code' or config['engine'].get('claude')!=frozen
        or runtime['id']!=frozen['runtimeProfileId'] or runtime['sha256']!=frozen['sha256']
        or runtime['sdkVersion']!=frozen['sdkVersion'] or runtime['sdkArchiveSha256']!=frozen['sdkArchiveSha256']):
        raise ProjectFault('The original Claude runtime binding changed. No model was started.',409)
    root=prepared['paths']['runtime']/identity(worker.run_id);private(root,directory=True,create=True)
    provider=AuthStore(worker.manifest['providers']).get(config['providerId'])
    home=auth_home(AuthStore(worker.manifest['providers']),provider['id'])
    # Native auth operations never mount this session's Projects directory.
    # Logout/refresh remains native and cannot remove another session's history.
    private(home/'Config/projects',directory=True,create=True)
    binding={'providerId':provider['id'],'studioSessionId':worker.session_id,'nativeSessionId':frozen['nativeSessionId'],
        'runId':worker.run_id,'requestId':worker.row['request_id'],'ownerType':worker.store.owner_type,
        'ownerId':worker.store.owner_id,'model':config['model'],'toolProfile':config['engine']['profile']}
    if binding!=broker.binding:raise ProjectFault('The original native bridge binding changed.',409)
    tools=[{'name':t['name'][7:],'description':t['description'],'inputSchema':t['inputSchema']}
        for t in specifications(config['engine']['profile'])]
    goal=getattr(worker,'claude_goal',None)
    live=config.get('claudeGoalPreparation') is True
    if goal or live:
        from claude_goal import REPORT_TOOL
        tools.append(REPORT_TOOL)
    write_new(root/'tools.json',{'schema':1,'binding':binding,'tools':tools})
    from instructions import compose
    prompt=compose(config)
    if 'claudeInstructions' in config:
        from claude_inputs import sha
        from claude_runtime import input_profile
        source=config['claudeInstructions'];raw=prompt.encode()
        if source!={'profileId':input_profile()['id'],'sha256':sha(raw),'bytes':len(raw)}:
            raise ProjectFault('The frozen native Claude instructions changed. No input was submitted.',409)
    prompt+='\n\nSTUDIO CLAUDE TOOL CONTRACT: Use only mcp__studio__ tools. Native file, shell, web, agent, memory, scheduler, plugin and computer tools are unavailable. Studio owns tool permissions and original receipts; never repeat an unconfirmed effect. The host alone owns native authentication, limits and resume.'
    if goal:
        prompt+='\n\nBOUNDED STUDIO GOAL: The next human input is the original saved objective activated by Play. Work only within its existing authority and tool permissions. Before ending each step call mcp__studio__report_goal with continue, complete or blocked and a concise reason. A report grants no new scope. The host may continue the same objective for at most eight steps and 900 active seconds per Play; never create your own scheduler or autonomous loop.'
    elif live:
        prompt+='\n\nSTUDIO GOAL PREPARATION: Only the first input in this query is an ordinary request; do not call report_goal for that input. A later host input headed STUDIO GOAL ACTIVATION with its Play execution ID identifies the explicitly activated saved Studio GOAL after the ordinary response. During that GOAL and its host-authorized continuation inputs, call mcp__studio__report_goal with continue, complete or blocked once before ending each step. That reserved status facet is available during an activated GOAL even when every project tool is disabled; it grants no project permissions. The host independently enforces activation, input receipts and at most eight steps and 900 active seconds per Play. Keep the original scope and permissions; never create a scheduler or autonomous loop.'
    from claude_inputs import prepared_input
    native_input=prepared_input(worker.store,worker.session_id,worker.run_id,config)
    if native_input:write_new(root/'input.json',native_input,12582912+4096)
    write_new(root/'runtime.json',{'schema':1,'binding':binding,'mode':prepared['mode'],'historyConfirmed':prepared['historyConfirmed'],
        **({'inputContract':{key:native_input[key] for key in ('profileId','requestId','textSha256','contentSha256')}} if native_input else {}),
        'requireInputReceipt':bool(getattr(worker,'queued_input',False) or goal or live or config.get('claudeInput')),
        **({'retryProtocol':1} if type(config.get('claudeRetryProtocol')) is int and config['claudeRetryProtocol']==1 else {}),
        **({'liveGoalPreparation':True} if live else {}),
        **({'goal':{key:config['claudeGoalExecution'][key] for key in ('executionId','maxSteps','maxActiveSeconds')}} if goal else {}),
        'effort':config.get('claudeModel',{}).get('effort',''),
        'resolvedModel':config.get('claudeModel',{}).get('resolvedModel'),
        'tools':[t['name'] for t in tools],'envelopedTools':[t['name'] for t in tools if t['inputSchema'].get('oneOf') or t['inputSchema'].get('anyOf')],
        'systemPrompt':prompt,'capability':broker.capability})
    source=Path(__file__).resolve().parent
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--share-net','--clearenv',
        '--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--symlink','usr/bin','/bin',
        '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run','--dir','/inference','--chdir','/inference',
        '--dir','/home','--bind',str(home/'Home'),'/home/studio','--bind',str(home/'Config'),'/config',
        '--bind',str(prepared['paths']['history']),'/config/projects',
        '--ro-bind',str(Path(runtime['sdk']).parent),'/runtime/sdk','--ro-bind',str(Path(runtime['native']).parent),'/runtime/native',
        '--ro-bind',str(root/'tools.json'),'/bridge/tools.json','--ro-bind',str(root/'runtime.json'),'/bridge/runtime.json',
        '--ro-bind',str(broker.path),'/bridge/host.sock','--ro-bind',str(source/'claude_mcp.py'),'/bridge/mcp.py',
        '--setenv','HOME','/home/studio','--setenv','USER','r4os-studio','--setenv','CLAUDE_CONFIG_DIR','/config','--setenv','PATH','/usr/bin']
    for path in ('/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf','/etc/ssl/certs'):
        if Path(path).exists():args+=['--ro-bind',path,path]
    if native_input:args+=['--ro-bind',str(root/'input.json'),'/bridge/input.json']
    for name in ('claude_engine.mjs','claude_session_engine.mjs','claude_session_io.mjs','claude_content.mjs'):
        args+=['--ro-bind',str(source/name),'/runtime/'+name]
    return ['/usr/bin/python3','-B',str(source/'claude_launch.py'),*args[1:],
        '--','/usr/bin/node','/runtime/claude_session_io.mjs']
