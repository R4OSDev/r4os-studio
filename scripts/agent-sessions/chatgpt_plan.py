"""Verified SIWC registrations, private renewal, and existing API credential leases."""
import asyncio
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import uuid
from urllib.parse import urlsplit,parse_qs

from api_provider_store import ApiProviders,private,key
from profile import directory,regular,write_json
from session_store import identity,encode,now
from store import ProjectFault

BASE='https://api.openai.com/v1'
SCOPES={'resource.invoke','chatgpt.tokens.use.direct'}
PREFIX='studio-plan-grant:'
SCRIPT=Path(__file__).with_name('chatgpt_plan_auth.mjs')


def require(value):
    if any(value.get(k)!=v for k,v in {'kind':'chatgpt-plan','baseUrl':BASE,'protocol':'responses','auth':'bearer','server':'custom'}.items()):
        raise ProjectFault('ChatGPT plan access requires its verified registration and the direct Responses endpoint.',409)


class Plan:
    def __init__(self,providers):self.api=ApiProviders(providers);self.root=Path(providers)/'ChatGPTPlan';self.processes={}

    def folder(self,name=None):
        private(self.api.parent,directory=True)
        root=directory(self.root);private(root,directory=True)
        child=directory(root/name) if name else root;private(child,directory=True)
        return child

    def read(self,path):
        try:
            private(path)
            if path.stat().st_size>131072:raise ProjectFault('The original ChatGPT account record exceeds its limit.',409)
            return json.loads(regular(path).read_text())
        except (OSError,ValueError,TypeError):raise ProjectFault('The private ChatGPT account record is unavailable. Original data was preserved.',409) from None

    @contextmanager
    def lock(self,path):
        fd=os.open(path,os.O_CREAT|os.O_NOFOLLOW|os.O_RDWR,0o600)
        with os.fdopen(fd,'a') as file:
            fcntl.flock(file,fcntl.LOCK_EX);yield

    def host(self):
        path=self.folder()/'Host.json'
        with self.lock(self.root/'Host.lock'):
            if not path.exists():write_json(path,{'hostId':'urn:uuid:'+str(uuid.uuid4())})
            value=self.read(path)['hostId'];identity(value.removeprefix('urn:uuid:'))
            return value

    def grant(self,ident):
        ident=identity(ident);return self.folder('Grants')/(ident+'.json')

    def registration(self,value):
        if (value.get('schema')!=1 or value.get('kind')!='studio-siwc' or value.get('issuer')!='https://auth.openai.com'
                or not isinstance(value.get('client_id'),str) or value['client_id']=='dynamic_agent_client'
                or not isinstance(value.get('subject'),str) or not isinstance(value.get('scopes'),list)
                or any(not isinstance(s,str) for s in value['scopes']) or not SCOPES<=set(value['scopes'])):
            raise ProjectFault('This registration has no confirmed permission for direct ChatGPT plan use. Sign in explicitly with Studio.',409)
        if any(not isinstance(s,str) for s in value['scopes']):raise ProjectFault('The original token scopes are unavailable.',409)
        for field in ('access_token','refresh_token'):key(value.get(field))
        return {k:value[k] for k in ('issuer','subject','client_id','ext_agent_host_id')}

    def prior(self,provider_id):
        values=[self.read(p) for p in self.folder('Grants').glob('*.binding.json') if self.read(p).get('providerId')==provider_id]
        if not values:raise ProjectFault('This selected account has no original Studio registration.',409)
        return max(values,key=lambda v:v['credentialRevision'])

    def frozen(self,provider):
        require(provider)
        with self.api.connect() as db:
            row=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',(provider['id'],provider['credentialRevision'])).fetchone()
            if not row or not row[0].startswith(PREFIX):raise ProjectFault('The original ChatGPT registration lease is unavailable.',409)
            ident=identity(row[0][len(PREFIX):])
        path=self.grant(ident);binding=self.read(path.with_suffix('.binding.json'));value=self.read(path)
        registered=self.registration(value)
        if binding['providerId']!=provider['id'] or binding['credentialRevision']!=provider['credentialRevision'] or binding['identity']!=registered:
            raise ProjectFault('The original ChatGPT account or workspace registration changed.',409)
        return {'grantId':ident,**registered}

    def invoke(self,config):
        # Tokens and paths never enter argv or ambient tool environments.
        child=subprocess.Popen(['/usr/bin/node',str(SCRIPT)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},start_new_session=True)
        status=Path(config['statusPath']);self.processes[str(status)]=child
        try:
            original=self.read(status) if status.exists() else {'state':'intent'}
            from attachment_store import birth
            write_json(status,{**original,'child':{'pid':child.pid,'birth':birth(child.pid)}})
            output,_=child.communicate((encode(config)+'\n').encode(),timeout=65)
            saved=self.read(status);write_json(status,{**saved,'processEnd':{'confirmed':True,'exitCode':child.returncode}})
            if child.returncode or len(output)>16384:raise ProjectFault('The original ChatGPT account operation could not be confirmed. No request was repeated.',409)
        except subprocess.TimeoutExpired:
            child.kill();child.communicate()
            raise ProjectFault('The original ChatGPT account operation exceeded its deadline. Reauthorize explicitly; no request was repeated.',409) from None
        finally:
            if child.poll() is None:child.kill();child.communicate()
            self.processes.pop(str(status),None)

    def credential(self,provider,frozen):
        if self.frozen(provider)!=frozen:raise ProjectFault('The original ChatGPT grant identity changed. No model request was started.',409)
        path=self.grant(frozen['grantId'])
        with self.lock(path.with_suffix('.lock')):
            binding=self.read(path.with_suffix('.binding.json'))
            if binding.get('refresh'):
                previous=self.read(self.folder('Operations')/(binding['refresh']+'.json'))
                if previous.get('state') not in ('authorized','permissionMissing'):
                    raise ProjectFault('The original rotating ChatGPT token refresh is unconfirmed. Sign in again explicitly.',409)
            value=self.read(path)
            if self.registration(value)!={k:frozen[k] for k in ('issuer','subject','client_id','ext_agent_host_id')}:
                raise ProjectFault('The original ChatGPT account or host identity changed.',409)
            if datetime.fromisoformat(value['expires_at']).timestamp()<=datetime.now(timezone.utc).timestamp()+60:
                rid=str(uuid.uuid4());binding['refresh']=rid
                status=self.folder('Operations')/(rid+'.json');write_json(status,{'state':'intent','createdAt':now()})
                write_json(path.with_suffix('.binding.json'),binding)
                self.invoke({'mode':'refresh','path':str(path),'hostId':frozen['ext_agent_host_id'],'statusPath':str(status)})
                if self.read(status).get('state')!='authorized':raise ProjectFault('The renewed ChatGPT grant has no direct plan permission. No model request was started.',409)
                value=self.read(path)
            self.registration(value)
            return key(value['access_token'])

    def install(self,rid,grant_path,name,provider_id=None,expected_revision=None):
        rid=identity(rid);value=self.read(grant_path);registered=self.registration(value)
        if registered['ext_agent_host_id']!=self.host():raise ProjectFault('The imported registration must preserve this Studio host identity.',409)
        target=self.grant(rid);binding_path=target.with_suffix('.binding.json')
        source_hash=hashlib.sha256(encode(value).encode()).hexdigest()
        previous=None
        try:previous=self.api.receipt(provider_id,rid) if provider_id else self.api.creation_receipt(rid)
        except ProjectFault as error:
            if error.code!=404:raise
        if previous:
            result=previous
            if result['state']!='complete':raise ProjectFault('The original account install is still pending.',409)
        else:
            if target.exists() and self.read(target)!=value:raise ProjectFault('The original ChatGPT registration bytes changed.',409)
            if not target.exists():write_json(target,value)
            if provider_id:
                current=self.api.get(identity(provider_id));require(current)
                if expected_revision is not None and current['revision']!=expected_revision:raise ProjectFault('This connection changed after the original sign-in. Its authorization was preserved without reactivating the connection.',409)
                old=self.prior(provider_id)['identity']
                if any(old[k]!=registered[k] for k in ('issuer','subject','client_id')):raise ProjectFault('Reauthorization belongs to another selected account or workspace.',409)
                result=self.api.mutate('update',provider_id,{'requestId':rid,'revision':current['revision'],'key':PREFIX+rid,'enabled':True},plan=True)
            else:
                result=self.api.mutate('create',None,{'requestId':rid,'name':name,'kind':'chatgpt-plan','baseUrl':BASE,'protocol':'responses','auth':'bearer','server':'custom','key':PREFIX+rid},plan=True)
        provider=result['provider'];binding={'providerId':provider['id'],'credentialRevision':provider['credentialRevision'],'identity':registered,'sourceSha256':source_hash}
        if binding_path.exists():
            saved=self.read(binding_path)
            if any(saved.get(k)!=v for k,v in binding.items()):raise ProjectFault('The original grant binding changed.',409)
        else:write_json(binding_path,binding)
        return result

    def listing(self,owner=None):
        attempts=[]
        if self.root.exists() and (self.root/'Attempts').exists():
            for path in sorted((self.root/'Attempts').glob('*.json')):
                if path.name.endswith(('.status.json','.token.json')):continue
                attempt=self.read(path)
                if owner is not None and attempt.get('ownerId')!=owner:continue
                status_path=path.with_suffix('.status.json')
                state=self.read(status_path) if status_path.exists() else {'state':'starting'}
                if state['state'] in ('starting','waiting','exchanging','sent','intent'):
                    child=attempt.get('child') or state.get('child')
                    from attachment_store import birth
                    try:alive=bool(child) and (Path('/proc')/str(child['pid'])).stat().st_uid==os.getuid() and birth(child['pid'])==child['birth']
                    except (OSError,ValueError):alive=False
                    if not alive:state={'state':'unknown','error':'The original sign-in process ended without a confirmed registration.'}
                attempts.append({'requestId':attempt['requestId'],'name':attempt['name'],'state':state['state'],'registrationIssued':bool(state.get('issuedClientId')),'canFinish':state.get('planPermission') is True and not attempt.get('cancelRequested',False),
                    'redirectSubmitted':bool(attempt.get('redirectSubmission')),
                    **({'authorizationUrl':state['authorizationUrl']} if state['state']=='waiting' else {}),
                    **({'providerId':attempt['providerId']} if attempt.get('providerId') else {}),
                    **({'error':state['error']} if state.get('error') else {})})
        accounts=[];revocations={}
        for folder in ('Grants','Operations'):
            for path in (self.root/folder).glob('*.revoke.json'):
                record=self.read(path)
                if record.get('providerId'):revocations.setdefault(record['providerId'],[]).append(record.get('state'))
        for provider in self.api.listing():
            if provider['kind']!='chatgpt-plan':continue
            states=revocations.get(provider['id'],[]);revocation=None if not states else 'confirmed' if all(s=='revoked' for s in states) else 'unknown'
            try:
                grant=self.frozen(provider);value=self.read(self.grant(grant['grantId']))
                accounts.append({'providerId':provider['id'],'clientId':grant['client_id'],'email':value.get('email'),'directPermission':True,'remoteRevocation':revocation,
                    'quota':None,'usageUrl':'https://chatgpt.com/settings/usage'})
            except ProjectFault:
                try:client=self.prior(provider['id'])['identity']['client_id']
                except ProjectFault:client=None
                accounts.append({'providerId':provider['id'],**({'clientId':client} if client else {}),'directPermission':False,'remoteRevocation':revocation,'quota':None,'usageUrl':'https://chatgpt.com/settings/usage'})
        return {'accounts':accounts,'attempts':attempts,'nativeClaudeRequired':True}

    def revoke(self,provider_id):
        outcomes=[];targets={}
        with self.api.connect() as db:
            refs=[row[0][len(PREFIX):] for row in db.execute('SELECT value FROM secrets.credentials WHERE provider_id=?',(provider_id,)) if row[0].startswith(PREFIX)]
        for path in self.folder('Grants').glob('*.binding.json'):
            if self.read(path)['providerId']==provider_id:refs.append(path.name.removesuffix('.binding.json'))
        for ident in set(refs):
            target=self.grant(ident);targets[str(target)]=(target,target.with_suffix('.revoke.json'))
        for path in self.folder('Attempts').glob('*.json'):
            if path.name.endswith(('.status.json','.token.json')):continue
            attempt=self.read(path);token=path.with_suffix('.token.json')
            if attempt['input'].get('providerId')==provider_id and token.exists():targets[str(token)]=(token,self.folder('Operations')/(attempt['requestId']+'.revoke.json'))
        for target,status in targets.values():
            if status.exists():
                original=self.read(status)
                if original.get('state')=='revoked':outcomes.append(True);continue
                if original.get('state') in ('sent','unknown','intent'):outcomes.append(False);continue
            write_json(status,{'state':'intent','providerId':provider_id,'createdAt':now()})
            try:self.invoke({'mode':'revoke','path':str(target),'hostId':self.host(),'statusPath':str(status)})
            except ProjectFault:outcomes.append(False);continue
            confirmed=self.read(status).get('state')=='revoked';outcomes.append(confirmed)
            if confirmed:target.unlink()
        return {'remoteRevocation':'confirmed' if all(outcomes) else 'unknown','localDisconnected':True}


class Login:
    def __init__(self,providers):self.plan=Plan(providers);self.tasks={};self.children={};self.inputs={}
    def owner(self,owner):
        if not isinstance(owner,str) or len(owner)!=64 or any(c not in '0123456789abcdef' for c in owner):raise ProjectFault('Reload provider settings before signing in.',403)

    def owns(self,attempt,owner):
        if owner is not None:
            self.owner(owner)
            if attempt.get('ownerId')!=owner:raise ProjectFault('This original sign-in belongs to another browser session.',403)

    @property
    def busy(self):return bool(self.tasks)

    async def start(self,data,owner):
        if not isinstance(data,dict) or set(data)-{'requestId','name','providerId','previousAttempt'} or not {'requestId','name'}<=set(data):raise ProjectFault('Invalid ChatGPT sign-in request.',400)
        self.owner(owner)
        from api_provider_store import name as valid_name
        rid=identity(data['requestId']);name=valid_name(data['name']);host=self.plan.host();path=self.plan.folder('Attempts')/(rid+'.json')
        if path.exists():
            saved=self.plan.read(path)
            self.owns(saved,owner)
            if saved['input']!=data:raise ProjectFault('This original sign-in belongs to another input.',409)
            return self.plan.listing(owner)
        registration=None;issued=None;expected=None;consent=False;selected_revision=None
        if data.get('providerId'):
            provider=self.plan.api.get(identity(data['providerId']));require(provider);selected_revision=provider['revision']
            expected=self.plan.prior(provider['id'])['identity'];issued=expected['client_id']
            try:frozen=self.plan.frozen(provider);registration=self.plan.grant(frozen['grantId'])
            except ProjectFault:pass
        elif data.get('previousAttempt'):
            self.owns(self.plan.read(self.plan.folder('Attempts')/(identity(data['previousAttempt'])+'.json')),owner)
            prior=self.plan.folder('Attempts')/(identity(data['previousAttempt'])+'.status.json');previous=self.plan.read(prior);issued=previous.get('issuedClientId');consent=previous.get('state')=='permissionMissing'
            token_path=self.plan.folder('Attempts')/(identity(data['previousAttempt'])+'.token.json')
            if token_path.exists():registration=token_path
            elif self.plan.grant(data['previousAttempt']).exists():registration=self.plan.grant(data['previousAttempt'])
            if not issued:raise ProjectFault('The original sign-in has no issued registration to reuse.',409)
        token=path.with_suffix('.token.json');status=path.with_suffix('.status.json')
        write_json(path,{'requestId':rid,'name':name,'input':data,'providerRevision':selected_revision,'ownerId':owner,'createdAt':now()});write_json(status,{'state':'starting'})
        child=await asyncio.create_subprocess_exec('/usr/bin/node',str(SCRIPT),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},limit=32768)
        from attachment_store import birth
        attempt=self.plan.read(path);attempt['child']={'pid':child.pid,'birth':birth(child.pid)};write_json(path,attempt)
        config={'mode':'signin','path':str(token),'statusPath':str(status),'hostId':host}
        if registration:config['registrationPath']=str(registration)
        if issued:config['issuedClientId']=issued
        if expected:config['expectedIdentity']=expected
        if consent:config['requestConsent']=True
        child.stdin.write((encode(config)+'\n').encode());await child.stdin.drain()
        self.children[rid]=child
        async def observe():
            try:
                await child.wait();state=self.plan.read(status)
                state['processEnd']={'confirmed':True,'exitCode':child.returncode};write_json(status,state)
                if self.plan.read(path).get('cancelRequested'):
                    write_json(status,{**state,'upstreamState':state['state'],'state':'cancelled','error':'Sign-in was cancelled before activation. Review ChatGPT app access if authorization had already been sent.'})
                elif state.get('state')=='authorized':
                    write_json(status,{**state,'state':'activating'})
                    result=await asyncio.to_thread(self.plan.install,rid,token,name,data.get('providerId'),attempt.get('providerRevision'))
                    saved=self.plan.read(path);saved['providerId']=result['provider']['id'];write_json(path,saved)
                    write_json(status,{**self.plan.read(status),'state':'complete'})
                    if token.exists():token.unlink()
                elif state.get('state')=='exchanging':write_json(status,{**state,'state':'unknown'})
            except Exception:
                previous=self.plan.read(status);write_json(status,{**previous,'state':'unknown','error':'The original account setup could not be confirmed. Its private evidence was retained.'})
            finally:
                child.stdin.close()
                self.tasks.pop(rid,None);self.children.pop(rid,None)
        self.tasks[rid]=asyncio.create_task(observe())
        try:await asyncio.wait_for(child.stdout.readline(),5)
        except asyncio.TimeoutError:pass
        return self.plan.listing(owner)

    async def callback(self,rid,url,owner):
        self.owner(owner)
        rid=identity(rid);path=self.plan.folder('Attempts')/(rid+'.json');attempt=self.plan.read(path)
        self.owns(attempt,owner)
        try:size=len(url.encode()) if isinstance(url,str) else 0
        except UnicodeError:size=0
        if not 1<=size<=16384 or any(ord(c)<33 or ord(c)==127 for c in url):
            raise ProjectFault('Paste the complete redirect address from the browser address bar.',400)
        hashed=hashlib.sha256(url.encode()).hexdigest()
        if attempt.get('redirectSubmission'):
            if attempt['redirectSubmission']['sha256']!=hashed:raise ProjectFault('This original sign-in already received a different redirect. Read its status.',409)
            return self.plan.listing(owner)
        status=path.with_suffix('.status.json');state=self.plan.read(status);child=self.children.get(rid)
        if state.get('state')!='waiting' or rid not in self.tasks or child is None or child.returncode is not None:
            raise ProjectFault('This original sign-in is no longer waiting for a redirect. Read its status or start a new sign-in explicitly.',409)
        try:
            expected=parse_qs(urlsplit(state['authorizationUrl']).query,strict_parsing=True)
            callback=urlsplit(expected['redirect_uri'][0]);returned=urlsplit(url)
            fields=parse_qs(returned.query,keep_blank_values=True,strict_parsing=True)
            valid=(returned.scheme,returned.netloc,returned.path)==(callback.scheme,callback.netloc,callback.path) and not returned.fragment
            valid=valid and bool(fields) and all(len(v)==1 for v in fields.values()) and not set(fields)-{'code','state','client_id','scope','error','error_description','error_uri'}
            valid=valid and hmac.compare_digest(fields.get('state',[''])[0],expected['state'][0])
            valid=valid and bool(fields.get('code',[''])[0])!=bool(fields.get('error',[''])[0])
        except (ValueError,KeyError,TypeError):valid=False
        if not valid:raise ProjectFault('This redirect does not match the original sign-in. Copy its complete final 127.0.0.1 address, including the query.',400)
        # Receipt before forwarding. A lost pipe/HTTP response is observed using
        # this same attempt; never submit a second code after uncertain exchange.
        attempt['redirectSubmission']={'sha256':hashed,'createdAt':now()};write_json(path,attempt)
        try:
            child.stdin.write((encode({'callbackUrl':url})+'\n').encode());await child.stdin.drain()
        except (BrokenPipeError,ConnectionResetError):
            raise ProjectFault('Delivery to the original sign-in process is unconfirmed. Read its status; the code was not repeated.',409) from None
        return self.plan.listing(owner)

    async def finish(self,rid,owner=None):
        rid=identity(rid);path=self.plan.folder('Attempts')/(rid+'.json');attempt=self.plan.read(path)
        self.owns(attempt,owner)
        if rid in self.tasks or attempt.get('providerId'):return self.plan.listing(owner)
        proof=self.plan.read(path.with_suffix('.status.json'))
        if proof.get('planPermission') is not True or attempt.get('cancelRequested'):raise ProjectFault('This original registration is not confirmed. No import was repeated.',409)
        original=path.with_suffix('.token.json') if 'importId' not in attempt['input'] else self.plan.grant(rid)
        result=await asyncio.to_thread(self.plan.install,rid,original,attempt['name'],attempt['input'].get('providerId'),attempt.get('providerRevision'))
        attempt['providerId']=result['provider']['id'];write_json(path,attempt)
        status=path.with_suffix('.status.json');write_json(status,{**self.plan.read(status),'state':'complete'})
        if original!=self.plan.grant(rid) and original.exists():original.unlink()
        return self.plan.listing(owner)

    async def cancel_provider(self,provider_id):
        for rid in list(self.tasks):
            path=self.plan.folder('Attempts')/(rid+'.json')
            original=self.plan.read(path)['input'] if path.exists() else self.inputs.get(rid,{}).get('input',{})
            if original.get('providerId')==provider_id:await self.cancel(rid)

    async def cancel(self,rid,owner=None):
        rid=identity(rid);path=self.plan.folder('Attempts')/(rid+'.json');attempt=self.plan.read(path)
        self.owns(attempt,owner)
        task=self.tasks.get(rid)
        if not task or self.plan.read(path.with_suffix('.status.json')).get('state')=='activating':return self.plan.listing(owner)
        attempt['cancelRequested']=True;write_json(path,attempt)
        child=self.children.get(rid) or self.plan.processes.get(str(path.with_suffix('.status.json')))
        if child and child.returncode is None:
            try:child.terminate()
            except ProcessLookupError:pass
        try:await asyncio.wait_for(asyncio.shield(task),25)
        except asyncio.TimeoutError:
            if child:
                child.kill()
                if isinstance(child,asyncio.subprocess.Process):await child.wait()
                else:await asyncio.to_thread(child.wait)
            await task
        return self.plan.listing(owner)
