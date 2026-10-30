"""Original-worker Claude controls over the common private Goal transport."""
import asyncio
import json
import os
import socket
import struct
import time

from claude_goal import digest
from claude_goal_store import pending_controls, snapshot, write
from goal_store import Goals
from run_store import get_run
from session_store import encode, identity
from store import ProjectFault


class ClaudeGoalControl:
    def __init__(self,runtime):
        self.runtime=runtime;self.w=runtime.w;self.goals=Goals(self.w.store)
        self.server=None;self.lock=asyncio.Lock();self.handlers=set();self.closed=False

    async def start(self):
        self.server=await asyncio.start_unix_server(self.connection,path='\0r4os-studio-goal-'+self.w.run_id,limit=2049)

    def apply(self,rid):
        w=self.w;row=self.goals.command(w.session_id,rid);data=json.loads(row['payload'])
        if row['state']!='pending' or row['stage']!='accepted':return self.goals.receipt(w.session_id,rid)
        original=self.runtime.journal.read();spec=original['contract'];bound=original['binding']
        expected={'runId':w.run_id,'executionId':spec['executionId'],'nativeSessionId':spec['nativeSessionId'],
            'configSha256':bound['configSha256'],'worker':bound['worker']}
        client={k:v for k,v in data.items() if not k.startswith('_')}
        if (data.get('_claudeTarget')!=expected or data.get('action') not in ('pause','stop')
                or row['fingerprint']!=digest({'sessionId':w.session_id,**client})
                or json.loads(get_run(w.store,w.run_id)['worker'] or '{}')!=bound['worker']):
            raise ProjectFault('The original Claude Goal control binding changed. Nothing was repeated.',409)
        current=snapshot(self.goals,w.session_id)
        if not current['goal'] or current['goal'].get('executionId')!=spec['executionId']:
            raise ProjectFault('This control belongs to another original Claude Play.',409)
        if data['action']=='pause' and w.stopping and get_run(w.store,w.run_id)['state']=='stopping':
            return self.goals.finish(w.session_id,rid,'failed','A later explicit Stop superseded this Pause.',phase='pausing')
        # Only local authority changes here. Stage, original journal cause and
        # the public intent receipt commit together, before any Stop signal.
        with w.store.db:
            w.store.db.execute("UPDATE goal_commands SET stage='claude_worker_received' WHERE request_id=? AND state='pending' AND stage='accepted'",(rid,))
            self.runtime.journal.stop('The user '+('stopped' if data['action']=='stop' else 'paused')+' this original bounded Goal.',commit=False)
            value={**current['goal'],'status':'paused','updatedAt':int(time.time())}
            write(self.goals,w.session_id,value,'pausing',w.run_id)
            result=self.goals.finish(w.session_id,rid,phase='pausing')
        if data['action']=='stop':
            if w.broker:w.broker.stop_admission()
            w.defer_stop()
        return result

    async def drain(self):
        async with self.lock:
            for row in pending_controls(self.w):self.apply(row['request_id'])

    async def connection(self,reader,writer):
        if self.closed or len(self.handlers)>=4:writer.close();return
        task=asyncio.current_task();self.handlers.add(task)
        try:
            _,uid,_=struct.unpack('3i',writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid!=os.getuid():raise ProjectFault('The original Goal caller is unavailable.',403)
            raw=await asyncio.wait_for(reader.readline(),3)
            if len(raw)>2048 or not raw.endswith(b'\n'):raise ProjectFault('Invalid original Goal control.',400)
            value=json.loads(raw)
            if (not isinstance(value,dict) or set(value)!={'requestId','runId','sessionId'}
                    or value['runId']!=self.w.run_id or value['sessionId']!=self.w.session_id):
                raise ProjectFault('This Goal control belongs to another worker.',409)
            identity(value['requestId'])
            async with self.lock:result=self.apply(value['requestId'])
            response={'result':result}
        except asyncio.CancelledError:
            self.handlers.discard(task);writer.close()
            try:await writer.wait_closed()
            except OSError:pass
            raise
        except Exception as error:
            response={'error':str(error) if isinstance(error,ProjectFault) else 'The original Claude Goal control could not be confirmed. Read its original receipt.',
                'code':error.code if isinstance(error,ProjectFault) else 503}
        try:
            writer.write((encode(response)+'\n').encode());await writer.drain()
        except OSError:pass  # The original receipt outlives a disconnected caller.
        finally:
            self.handlers.discard(task);writer.close()
            try:await writer.wait_closed()
            except OSError:pass

    async def close(self):
        if self.closed:return
        self.closed=True
        # Serializing this marker with accepted control transactions prevents
        # the final native-result boundary from losing a newly accepted intent.
        try:
            async with self.lock:
                with self.w.store.db:
                    value=self.runtime.journal.read();value['controlOpen']=False;self.runtime.journal.save(value)
                for row in pending_controls(self.w):self.apply(row['request_id'])
        finally:
            if self.server:self.server.close();await self.server.wait_closed()
            handlers=self.handlers-{asyncio.current_task()}
            for task in handlers:task.cancel()
            if handlers:await asyncio.gather(*handlers,return_exceptions=True)
