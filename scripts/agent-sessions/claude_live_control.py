"""Delivered live intent on the original worker; no startup replay or new query."""
import asyncio
import json
import time
from types import SimpleNamespace

from claude_goal import digest, freeze, live_source_input
from claude_goal_control import ClaudeGoalControl
from claude_goal_store import saved_value, snapshot, write
from claude_live_store import close_source, mark, target
from run_store import get_run
from session_store import identity
from store import ProjectFault


class ClaudeLiveGoalControl(ClaudeGoalControl):
    def __init__(self,worker):
        super().__init__(SimpleNamespace(w=worker))
        self.arm_event=asyncio.Event();self.tasks=set();self.watcher=None

    async def start(self):
        await super().start()
        self.watcher=asyncio.create_task(self.watch())

    def launch(self,coroutine):
        task=asyncio.create_task(coroutine);self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def apply(self,rid):
        w=self.w;row=self.goals.command(w.session_id,rid);data=json.loads(row['payload'])
        if not data.get('_claudeLiveTarget'):return super().apply(rid)
        if row['state']!='pending' or row['stage']!='accepted':return self.goals.receipt(w.session_id,rid)
        client={k:v for k,v in data.items() if not k.startswith('_')}
        if (self.closed or w.done.is_set() or w.stopping or w.claude_goal
            or data['action'] not in ('save','play') or data['_claudeLiveTarget']!=target(w.store,w.session_id,get_run(w.store,w.run_id))
            or row['fingerprint']!=digest({'sessionId':w.session_id,**client})):
            raise ProjectFault('The original live Claude response changed. Read its receipt; no Play was repeated.',409)
        if data['action']=='save':
            value=saved_value(w.store,w.session_id,snapshot(self.goals,w.session_id)['goal'],data['objective'])
            with w.store.db:
                w.store.db.execute("UPDATE goal_commands SET stage='claude_worker_received' WHERE request_id=?",(rid,))
                write(self.goals,w.session_id,value,run_id=w.run_id)
                return self.goals.finish(w.session_id,rid)
        from claude_goal_worker import ClaudeGoalRuntime
        spec=freeze(w.store,w.session_id,row);runtime=ClaudeGoalRuntime(w,spec)
        runtime.start();runtime.control=self
        with w.store.db:
            w.store.db.execute("UPDATE goal_commands SET stage='claude_worker_received' WHERE request_id=?",(rid,))
            mark(w,'waiting',rid)
        self.runtime=runtime;w.claude_goal=runtime
        self.launch(self.arm())
        return self.goals.receipt(w.session_id,rid)

    async def arm(self):
        try:
            spec=self.runtime.journal.spec
            await self.w.command('arm_goal',**{k:spec[k] for k in ('executionId','objective','maxSteps','maxActiveSeconds')})
            # Waiting for this receipt in read_native would deadlock its reader.
            await asyncio.wait_for(self.arm_event.wait(),10)
            self.maybe_begin()
        except asyncio.CancelledError:raise
        except Exception:
            self.w.uncertain_effect=True
            self.w.error='The original live Goal preparation is unconfirmed. It was not repeated.'
            self.w.defer_stop()

    def native_arm(self,frame):
        runtime=self.w.claude_goal
        if not runtime or not runtime.live:raise ProjectFault('Unexpected native Goal preparation receipt.',409)
        spec=runtime.journal.spec
        if frame.get('requestId')!=self.w.row['request_id'] or frame.get('executionId')!=spec['executionId']:
            raise ProjectFault('The native live Goal receipt belongs to another request.',409)
        accepted=frame['event']=='goal_armed'
        if accepted and (frame.get('nativeSessionId')!=spec['nativeSessionId']
            or frame.get('sourceInputRequestId')!=live_source_input(runtime.journal.binding) or frame.get('state')!='waiting'):
            raise ProjectFault('The native live Goal source binding changed.',409)
        value=runtime.journal.read();source=value['liveSource']
        if source['armed'] or source['armRefused']:raise ProjectFault('Duplicate native Goal preparation receipt.',409)
        source.update(armed=accepted,armRefused=not accepted)
        with self.w.store.db:runtime.journal.save(value)
        self.arm_event.set();self.maybe_begin()

    def source_result(self,native,reported=None):
        runtime=self.runtime;value=runtime.journal.read();source=value['liveSource']
        if source['result'] is not None:raise ProjectFault('The original live Goal source result was duplicated.',409)
        identity(native.get('uuid'))
        if native.get('session_id')!=runtime.journal.binding['nativeSessionId']:raise ProjectFault('The live Goal source session changed.',409)
        physical=runtime.journal.binding.get('sourceInput')
        if physical:
            reported=reported or {};retry=reported.get('nativeRetry') or {}
            if (reported.get('studioRequestId')!=runtime.journal.binding['requestId']
                or reported.get('nativeSessionId')!=runtime.journal.binding['nativeSessionId']
                or reported.get('nativeType')!='result' or reported.get('nativeMessageId')!=native['uuid']
                or reported.get('nativeInputRequestIds') not in ([],[physical['inputId']])
                or retry.get('schema')!=1 or digest(retry.get('claim'))!=physical['claimSha256']):
                raise ProjectFault('The live Goal result is not bound to its confirmed retry input.',409)
        source.update(result={'id':native['uuid'],'subtype':native.get('subtype'),'isError':native.get('is_error') is True},
            inputConfirmed=self.w.input_receipt.is_set())
        if physical:source['result']['inputId']=physical['inputId']
        with self.w.store.db:runtime.journal.save(value)
        self.maybe_begin()

    def maybe_begin(self):
        if self.closed or self.w.done.is_set() or not self.w.claude_goal or self.runtime.begun:return
        source=self.runtime.journal.read()['liveSource']
        if source['result'] and (source['armed'] or source['armRefused']) and not getattr(self,'begin_task',None):
            self.begin_task=True;self.launch(self.begin())

    async def begin(self):
        w=self.w;runtime=self.runtime
        try:
            async with self.lock:
                await self.drain_unlocked()
                value=runtime.journal.read();source=value['liveSource'];result=source['result']
                from message_store import pending_queue
                queued=pending_queue(w.store,w.session_id,authorized=True)
                safe=(source['armed'] and source['inputConfirmed'] and result['subtype']=='success' and not result['isError']
                    and value['state']=='admitting' and not w.stopping and not w.uncertain_effect and not queued
                    and not w.store.db.execute("SELECT 1 FROM tools WHERE run_id=? AND (result IS NULL OR state IN ('intent','unknown') OR json_extract(result,'$.partialChangesPossible')=1 OR json_extract(result,'$.error')='unknown')",(w.run_id,)).fetchone())
                if safe:safe=await w.current(w.broker.binding)
                if not safe:
                    if queued:runtime.journal.stop('Queued messages take priority after the original response.')
                    elif value['state']=='admitting' and not source['armRefused']:
                        runtime.journal.stop('The original response could not authorize the waiting Goal.')
                    self.finish_source();return
                # Durable at-most-once boundary before the native pipe write.
                source['beginSent']=True
                with w.store.db:runtime.journal.save(value)
                runtime.begun=True;w.input_receipt.clear()
                w.admission_started_at=time.time();w.admission_denial=None
                mark(w,'goal',runtime.journal.spec['executionId'])
                await w.command('begin_goal',executionId=runtime.journal.spec['executionId'])
        except asyncio.CancelledError:raise
        except Exception:
            w.uncertain_effect=True;w.error='The original live Goal boundary is unconfirmed. No new Play was submitted.';w.defer_stop()

    def finish_source(self):
        native=self.w.native_result or {}
        self.w.outcome=('unknown' if self.w.uncertain_effect else 'interrupted') if self.w.stopping else (
            'completed' if native.get('subtype')=='success' and not native.get('is_error') else 'failed')
        self.w.done.set()

    async def drain_unlocked(self):
        from claude_goal_store import pending_controls
        for row in pending_controls(self.w):self.apply(row['request_id'])

    async def watch(self):
        try:
            while not self.w.done.is_set():
                if self.w.claude_goal:await self.drain()
                await asyncio.sleep(.25)
        except asyncio.CancelledError:pass
        except Exception:
            self.w.uncertain_effect=True;self.w.defer_stop()

    def close_intent(self):
        close_source(self.w)
        # An accepted but never delivered command has no native authorization.
        from goal_store import exists
        if not exists(self.w.store):return
        for row in self.w.store.db.execute("SELECT * FROM goal_commands WHERE state='pending' AND stage='accepted'").fetchall():
            data=json.loads(row['payload'])
            if data.get('_claudeLiveTarget',{}).get('runId')==self.w.run_id:
                self.goals.finish(self.w.session_id,row['request_id'],'failed','The original Claude response ended before this command was delivered. Nothing was started.')

    async def close(self):
        if self.closed:return
        if self.w.claude_goal:await super().close()
        else:
            self.closed=True
            if self.server:self.server.close();await self.server.wait_closed()
            handlers=self.handlers-{asyncio.current_task()}
            for task in handlers:task.cancel()
            if handlers:await asyncio.gather(*handlers,return_exceptions=True)
        self.close_intent()
        tasks=(self.tasks|({self.watcher} if self.watcher else set()))-{asyncio.current_task()}
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
