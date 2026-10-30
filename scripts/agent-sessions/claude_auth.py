"""Only the pinned native CLI signs in, checks status and logs out of a plan."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import time
from urllib.parse import urlsplit,parse_qs

from api_provider_store import private
from claude_auth_store import AuthStore
from claude_runtime import installed
from session_store import identity,now
from store import ProjectFault

ANSI=re.compile(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]')


def native_url(text):
    for candidate in re.findall(r'https://[^\s\x1b]+',ANSI.sub('',text)):
        try:
            url=urlsplit(candidate);query=parse_qs(url.query,strict_parsing=True)
            if (url.scheme=='https' and url.netloc=='claude.com' and url.path=='/cai/oauth/authorize' and not url.fragment
                and set(query)=={'client_id','code','code_challenge','code_challenge_method','redirect_uri','response_type','scope','state'}
                and all(len(v)==1 for v in query.values()) and query['response_type']==['code']
                and query['code_challenge_method']==['S256'] and query['redirect_uri']==['https://platform.claude.com/oauth/code/callback']
                and re.fullmatch('[A-Za-z0-9_-]{16,256}',query['state'][0]) and len(candidate)<=4096):
                return candidate,query['state'][0]
        except ValueError:pass
    return None


def status_result(raw,returncode):
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or type(value.get('loggedIn')) is not bool or returncode not in (0,1):raise ValueError()
        if not value['loggedIn']:
            if returncode!=1 or value.get('authMethod')!='none':raise ValueError()
            return 'not-connected',None,'No Claude subscription is signed in.'
        if (returncode!=0 or value.get('authMethod')!='claude.ai' or value.get('apiProvider')!='firstParty'
            or value.get('apiKeySource') not in (None,'none') or value.get('configDirectory')!='/config'
            or value.get('forcedLoginMethod') not in (None,'claudeai')):
            return 'unsupported',None,'Native authentication does not select a Claude subscription. Model access remains unavailable.'
        plan=value.get('subscriptionType')
        if plan not in ('pro','max'):return 'unsupported',None,'Only a native Claude Pro or Max subscription is qualified at this stage.'
        account={'email':value.get('email'),'orgId':value.get('orgId'),'orgName':value.get('orgName'),'plan':plan,
            'authMethod':'claude.ai','apiProvider':'firstParty','checkedAt':now()}
        from claude_provider_store import valid_account
        if not valid_account(account,'connected') or not account['orgId'] or not account['email']:raise ValueError()
        return 'connected',account,'Claude subscription sign-in confirmed. Model and limit qualification is still pending.'
    except (ValueError,TypeError):
        raise ProjectFault('The native Claude authentication status could not be confirmed. Existing credentials were preserved.',503) from None


def auth_home(store,ident):
    root=store.root/identity(ident);private(root,directory=True,create=True)
    for name in ('Home','Config'):
        folder=root/name;private(folder,directory=True,create=True)
        count=0
        for base,dirs,files in os.walk(folder,followlinks=False):
            for name in dirs+files:
                count+=1
                if count>4096:raise ProjectFault('The native Claude auth directory exceeds its bound. Existing data was preserved.',503)
                item=Path(base)/name;private(item,directory=name in dirs)
    return root


def command(runtime,root,action,network=True):
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all']
    if network:args+=['--share-net']
    args+=['--clearenv','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--symlink','usr/bin','/bin',
        '--proc','/proc','--dev','/dev','--tmpfs','/tmp','--tmpfs','/run','--dir','/inference','--chdir','/inference',
        '--dir','/home','--bind',str(root/'Home'),'/home/studio','--bind',str(root/'Config'),'/config',
        '--ro-bind',runtime['native'],'/claude']
    for path in ('/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf','/etc/ssl/certs'):
        if Path(path).exists():args+=['--ro-bind',path,path]
    env={'PATH':'/usr/bin','HOME':'/home/studio','USER':'r4os-studio','CLAUDE_CONFIG_DIR':'/config','TERM':'dumb','NO_COLOR':'1',
        'DISABLE_AUTOUPDATER':'1','DISABLE_UPDATES':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1',
        'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1','ENABLE_CLAUDEAI_MCP_SERVERS':'false'}
    for key,value in env.items():args+=['--setenv',key,value]
    commands={'connect':['login','--claudeai'],'status':['status','--json'],'disconnect':['logout']}
    return args+['--','/claude','--setting-sources','','auth',*commands[action]]


class ClaudeAuth:
    def __init__(self,providers):self.store=AuthStore(providers);self.jobs={}

    @property
    def busy(self):return bool(self.jobs)

    async def start(self,ident,data,owner):
        ident=identity(ident)
        if len(self.jobs)>=2:raise ProjectFault('The native Claude authentication capacity is busy.',429)
        # Original receipts are read before verifying runtime or creating auth homes.
        result,fresh=self.store.begin(ident,data,owner)
        if fresh:
            job={'requestId':result['requestId'],'owner':owner,'cancel':False,'child':None,'url':None,'state':None,'submitted':False,'expires':time.monotonic()+300}
            self.jobs[ident]=job;job['task']=asyncio.create_task(self.run(ident,job,result))
        return self.view(ident,result['requestId'],owner)

    def view(self,ident,rid,owner):
        result=self.store.operation(ident,rid,owner);job=self.jobs.get(ident)
        if job and job['requestId']==rid and job['owner']==owner and job['url'] and not job['cancel'] and not job['submitted'] and time.monotonic()<job['expires']:
            return {**result,'state':'waiting','authorizationUrl':job['url'],'expiresInSeconds':max(0,int(job['expires']-time.monotonic()))}
        return result

    async def submit(self,ident,rid,owner,code):
        self.store.operation(ident,rid,owner);job=self.jobs.get(ident)
        if not job or job['requestId']!=rid or job['owner']!=owner or job['cancel'] or job['submitted'] or not job['state'] or time.monotonic()>=job['expires']:
            raise ProjectFault('This native sign-in no longer accepts a code. Read its original result.',409)
        if not isinstance(code,str) or not re.fullmatch(r'[A-Za-z0-9_.~-]{1,1536}#[A-Za-z0-9_-]{16,256}',code) or code.split('#')[1]!=job['state']:
            raise ProjectFault('Paste the complete code from this sign-in, including its state after #.',400)
        job['submitted']=True;job['url']=None
        try:job['child'].stdin.write((code+'\n').encode());await job['child'].stdin.drain()
        except (BrokenPipeError,ConnectionError):
            raise ProjectFault('The code handoff is unconfirmed. Read the original request; do not submit it again.',503) from None
        return self.view(ident,rid,owner)

    async def cancel(self,ident,rid,owner):
        result=self.store.operation(ident,rid,owner);job=self.jobs.get(ident)
        if result['state'] not in ('pending','waiting'):return result
        if not job or job['requestId']!=rid or job['owner']!=owner:
            raise ProjectFault('The original native sign-in process is unconfirmed. Explicitly check status.',409)
        job['cancel']=True;job['url']=None
        await self.kill(job)
        await asyncio.shield(job['task'])
        return self.view(ident,rid,owner)

    async def kill(self,job):
        child=job['child']
        if child and child.returncode is None:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            await asyncio.wait_for(child.wait(),3)

    async def execute(self,job,args,login=False):
        child=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE if login else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env={'PATH':'/usr/bin'},start_new_session=True,umask=0o077)
        job['child']=child
        if job['cancel']:await self.kill(job);raise asyncio.CancelledError()
        output=b'';deadline=job['expires'] if login else min(job['expires'],time.monotonic()+15)
        while True:
            part=await asyncio.wait_for(child.stdout.read(4096),max(.01,deadline-time.monotonic()))
            if not part:break
            output+=part
            if len(output)>32768:raise ValueError()
            if login and not job['submitted']:
                url=native_url(output.decode('utf-8','replace'))
                if url:job['url'],job['state']=url
        await asyncio.wait_for(child.wait(),max(.01,deadline-time.monotonic()))
        if job['cancel']:raise asyncio.CancelledError()
        return output,child.returncode

    async def run(self,ident,job,result):
        rid=result['requestId'];state='failed';message='The native Claude authentication request failed. Existing credentials were preserved.'
        status=None;account=None;usage=None
        try:
            runtime=await asyncio.to_thread(installed,self.store.parent);root=auth_home(self.store,ident)
            action=result['action']
            if action not in ('status','limits'):
                _,code=await self.execute(job,command(runtime,root,action),action=='connect')
                if code!=0:raise ValueError()
            raw,code=await self.execute(job,command(runtime,root,'status'))
            status,account,message=status_result(raw,code)
            if action=='limits' and status=='connected':
                from claude_limits_command import limits_command
                try:
                    output,usage_code=await self.execute(job,limits_command(runtime,root,rid))
                    report=json.loads(output)
                    if (usage_code!=0 or report.get('schema')!=1 or report.get('requestId')!=rid
                        or report.get('nativeVersion')!=runtime['version'] or report.get('sdkVersion')!=runtime['sdkVersion']
                        or report.get('promptMessagesSubmitted')!=0):raise ValueError()
                    sdk_account=report.get('account')
                    if (not isinstance(sdk_account,dict) or sdk_account.get('apiProvider')!='firstParty'
                        or sdk_account.get('email')!=account['email'] or sdk_account.get('apiKeySource') not in (None,'none')
                        or sdk_account.get('tokenSource') not in (None,'claude.ai')
                        or {'Claude Pro':'pro','Claude Max':'max','pro':'pro','max':'max'}.get(sdk_account.get('subscriptionType'))!=account['plan']):raise ValueError()
                    usage=report.get('usage')
                    after,after_code=await self.execute(job,command(runtime,root,'status'))
                    after_status,after_account,_=status_result(after,after_code)
                    from claude_provider_store import account_identity
                    if after_status!='connected' or account_identity(after_account)!=account_identity(account):
                        usage=None;status=after_status;account=after_account
                    message='Native subscription limits checked. Missing windows and unconfirmed extra usage remain unavailable.'
                except (ValueError,TypeError,asyncio.TimeoutError,OSError):
                    await self.kill(job)
                    message='Native subscription usage is unavailable. No model prompt was submitted.'
            auth_home(self.store,ident)
            if action=='disconnect' and status!='not-connected':raise ValueError()
            state='complete'
        except asyncio.CancelledError:
            state='cancelled';message='Native sign-in cancelled. Explicitly check status before using this provider.';status='reauthentication-required';account=None
            if result['action']=='limits':status=None;message='Native usage check cancelled. No model prompt was submitted.'
        except asyncio.TimeoutError:
            state='expired';message='The native authentication deadline elapsed. Explicitly check status before trying again.';status='reauthentication-required';account=None
            if result['action']=='limits':status=None;message='The native usage check deadline elapsed. No model prompt was submitted.'
        except (OSError,ValueError,TypeError,ProjectFault):
            status='reauthentication-required';account=None
        finally:
            try:
                await self.kill(job)
                self.store.finish(ident,rid,state,message,status,account,usage)
            finally:
                job['url']=None;job['state']=None;self.jobs.pop(ident,None)

    async def close(self):
        jobs=list(self.jobs.values())
        for job in jobs:job['cancel']=True;await self.kill(job)
        if jobs:await asyncio.gather(*(job['task'] for job in jobs),return_exceptions=True)
