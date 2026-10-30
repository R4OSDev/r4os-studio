"""Private per-run MCP authorization/effect boundary, independent of Codex RPC."""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import struct

from api_provider_store import private
from claude_mcp import identifier,MAX_REQUEST,MAX_RESULT
from session_store import encode


def failure(message):
    return {'content':[{'type':'text','text':encode({'success':False,'error':'unavailable','output':message})}],'isError':True}


class ClaudeToolBroker:
    def __init__(self,root,binding,tools,current,execute,admit=None):
        self.root=Path(root).absolute();self.binding=json.loads(encode(binding));self.tools=set(tools)
        self.current=current;self.execute=execute;self.capability=secrets.token_hex(32)
        self.admit=admit
        self.grants={};self.calls={};self.connections=set();self.server=None;self.closed=False

    async def start(self):
        private(self.root,directory=True,create=True)
        self.path=self.root/'host.sock'
        if self.path.exists() or self.path.is_symlink():raise ValueError('Preserve the original Claude broker socket until its run is reconciled.')
        self.server=await asyncio.start_unix_server(self.connection,path=str(self.path),limit=MAX_REQUEST+1)
        self.path.chmod(0o600)
        return self.path

    async def handle(self,value):
        if self.closed or not isinstance(value,dict) or value.get('binding')!=self.binding:
            return failure('This call does not belong to the original active Studio run.')
        operation=value.get('operation')
        if operation=='admit':
            if (set(value) not in ({'operation','binding','capability','account'},{'operation','binding','capability','account','usage'}) or not isinstance(value.get('capability'),str)
                or not hmac.compare_digest(value['capability'],self.capability) or not isinstance(value.get('account'),dict)
                or not await self.current(self.binding)):
                return {'allowed':False}
            if self.admit is None:return {'allowed':False,'reason':'Native subscription limit admission is not yet qualified.'}
            return await self.admit(self.binding,value['account'],value.get('usage'))
        fields={'operation','binding','tool','nativeToolUseId','arguments'}
        if operation=='authorize':fields.add('capability')
        if (set(value)!=fields or operation not in ('authorize','call') or not identifier(value.get('nativeToolUseId'))
            or not isinstance(value.get('tool'),str) or value['tool'] not in self.tools
            or not isinstance(value.get('arguments'),dict) or len(encode(value['arguments']).encode())>131072):
            return False if operation=='authorize' else failure('The original Studio tool call is outside its frozen binding.')
        if not await self.current(self.binding):return False if operation=='authorize' else failure('Original Studio tool admission is closed.')
        call_id=value['nativeToolUseId'];digest=hashlib.sha256(encode({'tool':value['tool'],'arguments':value['arguments']}).encode()).hexdigest()
        if operation=='authorize':
            capability=value.get('capability')
            if not isinstance(capability,str) or not hmac.compare_digest(capability,self.capability):return False
            old=self.grants.get(call_id)
            if len(self.grants)>=1024 or old is not None and old!=digest:return False
            self.grants[call_id]=digest;return True
        if self.grants.get(call_id)!=digest:return failure('The native tool-use identity and original permission grant do not match.')
        if call_id in self.calls:return await asyncio.shield(self.calls[call_id])
        if len(self.calls)>=4:return failure('The bound Studio tool concurrency limit is busy.')
        async def effect():
            # The existing common broker owns durable intent/result receipts,
            # permissions, images, Unknown and exact native-ID deduplication.
            return await self.execute('studio_'+value['tool'],value['arguments'],call_id)
        task=asyncio.create_task(effect());self.calls[call_id]=task
        try:return await asyncio.shield(task)
        finally:
            if task.done() and self.calls.get(call_id) is task:self.calls.pop(call_id,None)

    async def connection(self,reader,writer):
        task=asyncio.current_task();self.connections.add(task)
        try:
            sock=writer.get_extra_info('socket');_,uid,_=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=os.geteuid():raise ValueError()
            raw=await asyncio.wait_for(reader.readline(),10)
            if len(raw)>MAX_REQUEST or not raw.endswith(b'\n'):raise ValueError()
            result=await self.handle(json.loads(raw));output=encode({'result':result}).encode()+b'\n'
            if len(output)>MAX_RESULT:raise ValueError()
            writer.write(output);await writer.drain()
        except Exception:
            try:writer.write((encode({'result':failure('The original Studio tool result is unconfirmed. Read the original receipt; do not repeat an effect.')})+'\n').encode());await writer.drain()
            except (OSError,ConnectionError):pass
        finally:
            self.connections.discard(task);writer.close()
            try:await writer.wait_closed()
            except OSError:pass

    def stop_admission(self):self.closed=True;self.grants.clear()

    async def close(self):
        self.stop_admission()
        if self.server:self.server.close();await self.server.wait_closed()
        # Original effects finish under the worker's own Stop/Unknown boundary.
        # Closing a native pipe never launches or cancels another tool effect.
        if self.calls:await asyncio.gather(*list(self.calls.values()),return_exceptions=True)
        if self.connections:await asyncio.gather(*list(self.connections),return_exceptions=True)
        if self.server and self.path.exists():self.path.unlink()
        if self.server:
            try:self.root.rmdir()
            except OSError:pass  # Preserve any unexpected original files.
