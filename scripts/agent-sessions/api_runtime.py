"""Run-owned Responses transport and native launch binding, never a tool loop."""
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket

from api_endpoint import endpoint, resolved_addresses
from api_provider_store import private
from session_store import identity
from store import ProjectFault


def provider_name(ident):
    return 'studio_api_'+identity(ident).replace('-','_')


async def resolve_binding(binding):
    checked=endpoint(binding['baseUrl'],binding['kind'])
    from urllib.parse import urlsplit
    parsed=urlsplit(checked['baseUrl']);host=parsed.hostname;port=parsed.port or (443 if parsed.scheme=='https' else 80)
    try:
        try: addresses=[str(ipaddress.ip_address(host))]
        except ValueError:
            values=await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo,host,port,type=socket.SOCK_STREAM),10)
            addresses=[value[4][0] for value in values]
        return resolved_addresses(checked,addresses)
    except ProjectFault:raise
    except (OSError,ValueError,asyncio.TimeoutError):
        raise ProjectFault('The configured model endpoint could not be resolved safely.',503) from None


class ApiRuntime:
    def __init__(self,binding,model,credential,runtime,chat=None):
        self.binding=dict(binding);self.model=model;self.credential=credential
        self.chat=chat
        self.runtime=Path(runtime).absolute();self.child=None;self.port=None;self.key_file=None;self.key_inode=None
        identity(self.binding['id'])
        self.provider=provider_name(self.binding['id'])
        self.token=secrets.token_hex(32)
        self.reader=None;self.origins=[];self.usages=[];self.origin_error=False

    async def start(self):
        if self.binding['protocol'] not in ('responses','chat-completions') or self.binding['protocol']=='chat-completions' and not isinstance(self.chat,dict):
            raise ProjectFault('The selected API protocol has no qualified transport binding.',409)
        addresses=await resolve_binding(self.binding)
        self.runtime.mkdir(mode=0o700,parents=True,exist_ok=True);private(self.runtime,directory=True)
        self.key_file=self.runtime/'relay.key'
        fd=os.open(self.key_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            os.write(fd,self.token.encode());os.fsync(fd);self.key_inode=os.fstat(fd).st_ino
        finally:os.close(fd)
        try:
            self.child=await asyncio.create_subprocess_exec('/usr/bin/node',str(Path(__file__).with_name('api-transport.mjs')),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,limit=65536)
            data={'binding':{key:self.binding[key] for key in ('baseUrl','protocol','auth','kind')}|{'model':self.model},
                'addresses':addresses,'key':self.credential,'relayToken':self.token,'chatPolicy':self.chat}
            if self.binding['kind']=='openrouter':data['binding']['openrouter']=self.binding.get('openrouter')
            else:data['binding']['server']=self.binding.get('server','custom')
            self.child.stdin.write(json.dumps(data,separators=(',',':')).encode()+b'\n');await self.child.stdin.drain()
            ready=json.loads(await asyncio.wait_for(self.child.stdout.readline(),5))
            if set(ready)!={'port'} or type(ready['port']) is not int or not 1<=ready['port']<=65535:raise ValueError()
            self.port=ready['port']
            self.reader=asyncio.create_task(self.read_origins())
        except (OSError,ValueError,asyncio.TimeoutError,ConnectionError):
            await self.close();raise ProjectFault('The private model transport could not start.',503) from None

    def selection(self):return {'modelProvider':self.provider}

    async def read_origins(self):
        """Trusted relay usage/origin observations; never an inference/control channel."""
        fields={'event','ordinal','requestedModel','reportedRequested','reportedModel','reportedBackend','endpointModel','endpointBackend',
            'strategy','gatewayAttempt','providerResponseId','localResponseId','finishReason','usage'}
        try:
            while raw:=await self.child.stdout.readline():
                if len(raw)>8192:raise ValueError()
                value=json.loads(raw)
                if isinstance(value,dict) and value.get('event')=='usage':
                    if len(self.usages)>=256:
                        # Long Goal runs can outlive the bounded observation
                        # set. Keep draining the trusted relay; never create
                        # extra numeric receipts or leave its stdout unread.
                        self.origin_error=True;continue
                    if (set(value)!={'event','ordinal','responseId','usage'}
                            or type(value['ordinal']) is not int or not 1<=value['ordinal']<=256
                            or self.usages and value['ordinal']<=self.usages[-1]['ordinal']
                            or not isinstance(value['responseId'],str) or not 1<=len(value['responseId'].encode())<=256
                            or any(ord(c)<33 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in value['responseId'])
                            or isinstance(self.credential,str) and self.credential in value['responseId']):raise ValueError()
                    usage=value['usage']
                    if usage is not None and (not isinstance(usage,dict) or not usage
                            or set(usage)-{'input_tokens','output_tokens','total_tokens','cached_input_tokens','reasoning_output_tokens'}
                            or any(type(v) is not int or not 0<=v<=9007199254740991 for v in usage.values())):raise ValueError()
                    self.usages.append(value);continue
                if self.binding['kind']!='openrouter':raise ValueError()
                if len(self.origins)>=256:
                    self.origin_error=True;continue
                if (not isinstance(value,dict) or set(value)!=fields or value['event']!='origin'
                        or type(value['ordinal']) is not int or not 1<=value['ordinal']<=256
                        or self.origins and value['ordinal']<=self.origins[-1]['ordinal']
                        or value['requestedModel']!=self.model):raise ValueError()
                for field in fields-{'event','ordinal','gatewayAttempt','usage'}:
                    text=value[field]
                    if text is not None and (not isinstance(text,str) or not 1<=len(text.encode())<=256
                            or any(ord(c)<32 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in text)
                            or isinstance(self.credential,str) and self.credential in text):raise ValueError()
                attempt=value['gatewayAttempt']
                if attempt is not None and (type(attempt) is not int or not 1<=attempt<=32):raise ValueError()
                usage=value['usage']
                if usage is not None:
                    counters={'input_tokens','output_tokens','total_tokens'}
                    if not isinstance(usage,dict) or set(usage)-counters-{'input_tokens_details','output_tokens_details'} or not counters<=set(usage):raise ValueError()
                    if any(type(usage[k]) is not int or not 0<=usage[k]<=9007199254740991 for k in counters):raise ValueError()
                    for field,key in [('input_tokens_details','cached_tokens'),('output_tokens_details','reasoning_tokens')]:
                        if field in usage and (not isinstance(usage[field],dict) or set(usage[field])-{key}
                                or any(type(v) is not int or not 0<=v<=9007199254740991 for v in usage[field].values())):raise ValueError()
                self.origins.append({k:v for k,v in value.items() if k!='event'})
        except (OSError,ValueError,TypeError,UnicodeError):self.origin_error=True

    def arguments(self,original):
        if self.port is None or self.child is None or self.child.returncode is not None:
            raise ProjectFault('The original model transport is not available.',503)
        args=list(original);position=args.index('--chdir')
        args[position:position]=['--dir','/api','--ro-bind',str(self.key_file),'/api/relay.key',
            '--ro-bind',str(Path(__file__).with_name('api-model-launcher.py')),'/api/launcher.py']
        execute=args.index('/usr/bin/prlimit')+3
        if args[execute]!='/bin/codex':raise ProjectFault('The native model launch binding changed.',503)
        args[execute:execute+1]=['/usr/bin/python3','-I','-B','/api/launcher.py']
        settings={'name':'Studio API','base_url':f'http://127.0.0.1:{self.port}/v1','wire_api':'responses',
            'requires_openai_auth':False,'supports_websockets':False,'supports_standalone_web_search':False,
            'request_max_retries':0,'stream_max_retries':0,'env_key':'STUDIO_API_RELAY_TOKEN'}
        # A private provider ID is stable across runs of this API connection.
        # The changing loopback address and nonce never replace its thread ID.
        import json as wire
        pairs=[]
        for key,value in settings.items():pairs.append(key+'='+wire.dumps(value,separators=(',',':')))
        args+=['-c','model_provider='+wire.dumps(self.provider),'-c','model_providers.'+self.provider+'={'+','.join(pairs)+'}']
        return args

    async def close(self):
        if self.child:
            if self.child.stdin:self.child.stdin.close()
            if self.child.returncode is None:
                try:await asyncio.wait_for(self.child.wait(),2)
                except asyncio.TimeoutError:
                    self.child.terminate()
                    try:await asyncio.wait_for(self.child.wait(),2)
                    except asyncio.TimeoutError:self.child.kill();await self.child.wait()
        if self.reader:
            try:await asyncio.wait_for(asyncio.shield(self.reader),2)
            except asyncio.TimeoutError:
                self.origin_error=True;self.reader.cancel();await asyncio.gather(self.reader,return_exceptions=True)
        if self.key_file and self.key_inode is not None:
            try:
                private(self.key_file)
                if self.key_file.stat().st_ino==self.key_inode:self.key_file.unlink()
            except FileNotFoundError:pass
        self.credential=None;self.port=None
