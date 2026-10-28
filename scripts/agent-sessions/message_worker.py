"""User steering on the original native connection; no model tools or new turns."""
import asyncio
import json
import os
import socket
import struct

from attachment_store import birth
from codex_rpc import RPCRejected
from message_store import Messages, exists
from run_store import get_run
from session_store import encode
from store import ProjectFault


async def live_message(store, sid, request_id):
    messages = Messages(store); message = messages.row(sid, request_id)
    target = json.loads(message['input'])['target']
    run = get_run(store, target['runId'])
    if run['session_id'] != sid: raise ProjectFault('Message belongs to another session.', 403)
    worker = json.loads(run['worker'] or '{}')
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection('\0r4os-studio-messages-'+run['id'], limit=1048576), 3)
    try:
        pid, uid, _ = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != os.getuid() or pid != worker.get('pid') or birth(pid) != worker.get('birth') or worker.get('messageProtocol') != 1:
            raise ProjectFault('The original message worker identity changed.', 403)
        writer.write((encode({'requestId':request_id,'runId':run['id'],'sessionId':sid})+'\n').encode());await writer.drain()
        result = json.loads(await asyncio.wait_for(reader.readline(), 18))
        if 'error' in result: raise ProjectFault(result['error'], result.get('code',503))
        return result['result']
    finally:
        writer.close();await writer.wait_closed()


class MessageWorker:
    def __init__(self, worker):
        self.worker = worker;self.messages = Messages(worker.store)
        self.lock = asyncio.Lock();self.server = None;self.tasks = set();self.clients = set()

    async def start(self):
        self.server = await asyncio.start_unix_server(self.control, path='\0r4os-studio-messages-'+self.worker.run_id, limit=2049)

    def valid_target(self, row):
        w = self.worker; data = json.loads(row['input']); run = get_run(w.store,w.run_id)
        owner = json.loads(run['worker'] or '{}')
        if (row['mode'] != 'steer' or row['session_id'] != w.session_id or row['run_id'] != w.run_id
                or data['target'] != {'runId':w.run_id,'threadId':w.thread_id,'turnId':w.turn_id}
                or w.stopping or w.done.is_set() or run['state'] != 'running' or not run['busy']
                or owner.get('pid') != os.getpid() or owner.get('birth') != birth(os.getpid()) or owner.get('release') != w.manifest['release']
                or owner.get('messageTurnActive') is not True
                or json.loads(row['frozen'])['config'] != json.loads(run['config'])):
            raise ProjectFault('The original native turn changed or is stopping. The message was preserved.',409)
        return data

    async def deliver(self, request_id):
        w = self.worker
        async with self.lock:
            row = self.messages.row(w.session_id,request_id)
            if row['state'] != 'pending': return self.messages.present(row)
            try: data = self.valid_target(row)
            except ProjectFault as error: return self.messages.finish(w.session_id,request_id,'rejected',str(error))
            self.messages.finish(w.session_id,request_id,'dispatching')
            try:
                result = await w.client.request('turn/steer',{'threadId':w.thread_id,'expectedTurnId':w.turn_id,
                    'clientUserMessageId':request_id,'input':[{'type':'text','text':data['text']}]},timeout=10)
                if result.get('turnId') != data['target']['turnId']: raise RuntimeError('Unexpected native turn receipt.')
                return self.messages.finish(w.session_id,request_id,'accepted')
            except RPCRejected:
                return self.messages.finish(w.session_id,request_id,'rejected','The expected native turn rejected this message. Queue or resend explicitly after reviewing the current turn.')
            except asyncio.CancelledError:
                self.messages.finish(w.session_id,request_id,'unknown','The direct receipt was interrupted. This message was not submitted again.')
                raise
            except Exception:
                return self.messages.finish(w.session_id,request_id,'unknown','Native acceptance is unconfirmed. Inspect the original receipt; this message was not submitted again.')

    def observe(self, method, params):
        if method in ('turn/started','turn/completed'):
            w = self.worker; row = get_run(w.store,w.run_id)
            owner = json.loads(row['worker'] or '{}')
            owner['messageTurnActive'] = method == 'turn/started' and not w.stopping and not w.done.is_set()
            with w.store.db: w.store.db.execute('UPDATE runs SET worker=? WHERE id=?',(encode(owner),w.run_id))
        if method != 'item/completed' or not exists(self.worker.store): return
        item = params.get('item') or {}; key = item.get('clientId')
        if item.get('type') != 'userMessage' or not isinstance(key,str): return
        row = self.worker.store.db.execute("SELECT * FROM session_messages WHERE request_id=? AND session_id=? AND run_id=? AND mode='steer'",
            (key,self.worker.session_id,self.worker.run_id)).fetchone()
        if not row: return
        data = json.loads(row['input'])
        content = item.get('content',[])
        if (params.get('threadId') == data['target']['threadId'] and params.get('turnId') == data['target']['turnId']
                and len(content)==1 and content[0].get('type')=='text' and content[0].get('text') == data['text']):
            self.messages.finish(self.worker.session_id,key,'accepted')

    async def control(self, reader, writer):
        task = asyncio.current_task();self.tasks.add(task)
        if len(self.clients)>=4: writer.close();self.tasks.discard(task);return
        self.clients.add(writer);w=self.worker
        try:
            peer = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
            if struct.unpack('3i',peer)[1] not in (0,os.getuid()): raise ProjectFault('Message control peer is not authorized.',403)
            raw = await asyncio.wait_for(reader.readline(),3)
            if len(raw)>2048 or not raw.endswith(b'\n'): raise ProjectFault('Invalid message control frame.',400)
            data = json.loads(raw)
            if set(data)!={'sessionId','runId','requestId'} or data['sessionId']!=w.session_id or data['runId']!=w.run_id:
                raise ProjectFault('The message belongs to another worker.',403)
            result = {'result':await self.deliver(data['requestId'])}
            writer.write((encode(result)+'\n').encode());await writer.drain()
        except asyncio.CancelledError: raise
        except Exception as error:
            writer.write((encode({'error':str(error) if isinstance(error,ProjectFault) else 'The original message control could not be confirmed.','code':getattr(error,'code',503)})+'\n').encode())
            try: await writer.drain()
            except Exception: pass
        finally:
            self.tasks.discard(task);self.clients.discard(writer);writer.close()
            try: await writer.wait_closed()
            except Exception: pass

    async def close(self):
        if self.server: self.server.close();await self.server.wait_closed()
        for task in tuple(self.tasks): task.cancel()
        if self.tasks: await asyncio.gather(*self.tasks,return_exceptions=True)
