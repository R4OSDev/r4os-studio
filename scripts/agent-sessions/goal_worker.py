"""One admitted worker observes native continuation; it never loops turn/start."""
import asyncio
import json
import os
import socket
import struct
from goal_store import Goals
from session_store import encode
from store import ProjectFault


def end_turns(store, run_id):
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='goal_turns'").fetchone():
        with store.db: store.db.execute("UPDATE goal_turns SET status='unknown' WHERE run_id=? AND status='running'",(run_id,))


class GoalWorker:
    def __init__(self, worker, dormant=False):
        self.worker=worker;self.goals=Goals(worker.store);self.idle=asyncio.Event();self.idle.set()
        self.native=None;self.server=None;self.lock=asyncio.Lock();self.tasks=set();self.clients=set();self.activating=True
        self.evaluator=None;self.closed=False;self.last_turn_status=None
        self.generation=0
        self.armed=False;self.completed_once=False
        self.stop_reconcile=None
        self.queue_handoff=False
        self.dormant=dormant
        self.activation=worker.config.get('goalExecution')
        self.live_active_seen=False
        self.handlers=set()
        from goal_clock import GoalClock
        self.clock=GoalClock(worker)
        self.goals.schema()
        with worker.store.db:
            worker.store.db.execute('''CREATE TABLE IF NOT EXISTS goal_turns(
              run_id TEXT NOT NULL REFERENCES runs(id), turn_id TEXT NOT NULL,
              status TEXT NOT NULL, PRIMARY KEY(run_id,turn_id))''')

    async def read(self):
        w=self.worker
        generation=self.generation
        value=(await w.client.request('thread/goal/get',{'threadId':w.thread_id}))['goal']
        # A notification received while this read was in flight supersedes its
        # older snapshot, even when native timestamps share the same second.
        if generation!=self.generation: return self.native
        self.native=value;self.goals.observe(w.session_id,w.thread_id,value,w.run_id)
        self.measure()
        return value

    def measure(self):
        if self.armed and self.native and self.native['status']=='active' and self.activation:
            self.clock.start(self.activation['requestId'])
        if self.idle.is_set() and self.native and self.native['status']!='active':self.clock.end(unknown=self.worker.uncertain_effect)

    async def before_resume(self):
        w=self.worker
        if not w.thread_id: return
        # Read/neutralize saved active state while the native thread is unloaded.
        # Resume must not authorize any implicit old work before this Play.
        value=await self.read()
        if value and value['status']=='active':
            await w.client.request('thread/goal/set',{'threadId':w.thread_id,'status':'paused','origin':'automatic'})
            value=await self.read()
        if self.dormant:
            if value and value['status']=='active': raise ProjectFault('Saved Goal could not be paused before resume.',503)
            return
        if not value or value['objective']!=w.config['goalExecution']['objective'] or value['status']=='active':
            raise ProjectFault('The saved Goal changed before its worker started.',409)

    async def start_control(self):
        if self.server is None:
            self.server=await asyncio.start_unix_server(self.control,path='\0r4os-studio-goal-'+self.worker.run_id,limit=2049)
        if self.dormant: self.activating=False

    async def activate(self):
        w=self.worker;rid=w.config['goalExecution']['requestId']
        await self.start_control()
        self.goals.stage(w.session_id,rid,'native_activation');w.turn_requested=True
        self.armed=True
        try:
            await w.client.request('thread/goal/set',{'threadId':w.thread_id,'status':'active','origin':'user'})
        except Exception:
            value=await self.read()
            if not value or value['status']!='active': raise
        await self.read()
        self.goals.finish(w.session_id,rid)
        self.activating=False
        self.evaluate_later()

    def evaluate_later(self):
        if self.closed or (self.evaluator and not self.evaluator.done()): return
        task=asyncio.create_task(self.evaluate_safe());self.evaluator=task;self.tasks.add(task);task.add_done_callback(self.tasks.discard)

    async def evaluate_safe(self):
        try: await self.evaluate()
        except asyncio.CancelledError: raise
        except Exception:
            if not self.closed:
                self.worker.outcome='unknown';self.worker.error='The native Goal observation was lost. No new execution was submitted.'
                self.worker.done.set()

    async def evaluate(self):
        await asyncio.sleep(.05)
        if self.activating or self.lock.locked() or not self.idle.is_set() or self.worker.done.is_set(): return
        retry = getattr(self.worker, 'provider_retry', None)
        if retry and retry.state in ('waiting', 'submitting'): return
        if self.dormant:
            if self.last_turn_status and not self.retain_at_boundary():
                self.worker.outcome={'completed':'completed','interrupted':'interrupted','failed':'failed'}.get(self.last_turn_status,'unknown')
                self.worker.done.set()
            return
        value=await self.read()
        if (self.activating or self.lock.locked() or not self.idle.is_set() or self.worker.done.is_set()
                or retry and retry.state in ('waiting', 'submitting')): return
        if value is None or value['status']!='active':
            w=self.worker
            if self.retain_at_boundary(): return
            if w.uncertain_effect: w.outcome='unknown'
            elif self.queue_handoff and value and value['status']=='paused': w.outcome='completed'
            elif w.stopping or self.last_turn_status=='interrupted': w.outcome='interrupted'
            elif self.last_turn_status=='failed': w.outcome='failed';w.error=w.error or 'The native Goal turn failed.'
            else: w.outcome='completed'
            # Run completion only means this accepted execution ended. Native
            # Goal status remains paused/blocked/limited/complete as reported.
            self.goals.observe(w.session_id,w.thread_id,value,w.run_id,phase='unknown' if w.uncertain_effect else 'idle')
            w.done.set()

    def retain_at_boundary(self):
        # Serialize the acceptance/terminal boundary with the coordinator's
        # SQLite transaction. An accepted command wins; closing rejects later ones.
        w=self.worker
        w.store.db.execute('BEGIN IMMEDIATE')
        try:
            pending=w.store.db.execute("SELECT payload FROM goal_commands WHERE session_id=? AND state='pending'",(w.session_id,)).fetchall()
            if any(json.loads(r['payload']).get('target',{}).get('runId')==w.run_id for r in pending):
                # The coordinator may disappear before delivery. Revisit only
                # original status; this watcher never submits a native command.
                async def revisit():
                    await asyncio.sleep(.2)
                    self.evaluate_later()
                task=asyncio.create_task(revisit());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
                return True
            row=w.store.db.execute('SELECT worker FROM runs WHERE id=?',(w.run_id,)).fetchone()
            meta=json.loads(row['worker'] or '{}');meta['liveGoalOpen']=False
            w.store.db.execute('UPDATE runs SET worker=? WHERE id=?',(encode(meta),w.run_id))
            return False
        finally: w.store.db.commit()

    async def notify(self, method, params, retry_hold=False):
        w=self.worker
        if w.stopping and method in ('thread/goal/updated','thread/goal/cleared'):
            # A queued notification cannot undo a user Stop. Read native state
            # through the stopping worker instead of trusting an older event.
            if not self.closed and (not self.stop_reconcile or self.stop_reconcile.done()):
                task=asyncio.create_task(self.pause());self.stop_reconcile=task
                self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            return True
        if method=='thread/status/changed':
            status=params.get('status',{})
            if status.get('type')=='active' and set(status.get('activeFlags',[])) & {'waitingOnApproval','waitingOnUserInput'}:
                task=asyncio.create_task(self.pause());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            return True
        if method in ('thread/goal/updated','thread/goal/cleared'):
            self.generation+=1
            self.native=params.get('goal') if method.endswith('updated') else None
            if not self.dormant and self.native and self.native['status']=='active': self.live_active_seen=True
            self.goals.observe(w.session_id,w.thread_id,self.native,w.run_id)
            self.measure()
            if self.dormant and not self.activating and self.native and self.native['status']=='active':
                w.error='A native Goal was activated without a browser Play. Review the Goal before continuing.'
                w.defer_stop()
            if self.armed and self.native:
                changed=self.native['objective']!=self.activation['objective']
                restarted=self.completed_once and self.native['status']=='active'
                if changed or restarted:
                    w.stopping=True;w.error='The Goal changed during this execution. Review it before pressing Play.'
                    task=asyncio.create_task(w.stop());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
                if self.native['status']=='complete': self.completed_once=True
            self.evaluate_later();return True
        if method=='turn/started':
            self.idle.clear()
            with w.store.db: w.store.db.execute('INSERT INTO goal_turns VALUES (?,?,?) ON CONFLICT(run_id,turn_id) DO UPDATE SET status=excluded.status',
                (w.run_id,params['turn']['id'],'running'))
            from run_store import event
            event(w.store,w.session_id,w.run_id,'nativeTurn',{'id':params['turn']['id'],'status':'running'})
        elif method=='turn/completed':
            turn=params['turn'];w.turn_id=turn['id'];self.idle.set()
            self.last_turn_status=turn['status']
            self.measure()
            with w.store.db: w.store.db.execute('INSERT INTO goal_turns VALUES (?,?,?) ON CONFLICT(run_id,turn_id) DO UPDATE SET status=excluded.status',
                (w.run_id,turn['id'],turn['status']))
            from run_store import event
            event(w.store,w.session_id,w.run_id,'nativeTurn',{'id':turn['id'],'status':turn['status']})
            if retry_hold: return True
            if self.dormant: return self.retain_at_boundary()
            from message_store import pending_queue
            if turn['status']=='completed' and not w.stopping and pending_queue(w.store,w.session_id,authorized=True):
                # Pause outside the serial RPC reader. A racing continuation is
                # interrupted by the normal stopping admission before any tools.
                self.queue_handoff=True;w.stopping=True
                task=asyncio.create_task(self.pause());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            if turn['status'] in ('failed','interrupted'):
                task=asyncio.create_task(self.pause());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            self.evaluate_later();return True
        return False

    async def pause(self, origin='automatic'):
        w=self.worker
        if not w.client or not w.thread_id: return False
        try:
            value=await self.read()
            if value and value['status']=='active':
                await w.client.request('thread/goal/set',{'threadId':w.thread_id,'status':'paused','origin':origin},timeout=5)
                value=await self.read()
            if value and value['status']=='active': raise RuntimeError('Goal continuation remains unconfirmed.')
            if w.uncertain_effect:
                with w.store.db:
                    w.store.db.execute("UPDATE session_goals SET phase='unknown',reason=?,revision=revision+1 WHERE session_id=?",
                        ('A tool effect is unconfirmed. Inspect the original receipt before resuming this Goal.',w.session_id))
                    self.goals.publish(w.session_id)
        except Exception:
            with w.store.db:
                w.store.db.execute("UPDATE session_goals SET phase='unknown',reason=?,revision=revision+1 WHERE session_id=?",
                    ('Goal pause was not confirmed. No continuation was restarted.',w.session_id))
            w.uncertain_effect=True
            return False
        self.evaluate_later()
        return True

    async def control(self,reader,writer):
        if len(self.clients)>=4: writer.close();return
        self.clients.add(writer);w=self.worker
        handler=asyncio.current_task();self.handlers.add(handler)
        try:
            peer=writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12)
            if struct.unpack('3i',peer)[1] not in (0,os.getuid()): raise ProjectFault('Goal control peer is not authorized.',403)
            raw=await asyncio.wait_for(reader.readline(),3)
            if len(raw)>2048 or not raw.endswith(b'\n'): raise ProjectFault('Invalid Goal worker request.',400)
            data=json.loads(raw)
            if set(data)!={'sessionId','runId','requestId'} or data['sessionId']!=w.session_id or data['runId']!=w.run_id:
                raise ProjectFault('The Goal command belongs to another worker.',403)
            async with self.lock:
                row=self.goals.command(w.session_id,data['requestId']);command=json.loads(row['payload'])
                if command.get('target'):
                    await self.live_command(data['requestId'],row,command)
                    result={'result':self.goals.receipt(w.session_id,data['requestId'])}
                    writer.write((encode(result)+'\n').encode());await writer.drain()
                    self.evaluate_later()
                    return
                if command['action']=='play': raise ProjectFault('This worker cannot accept another Play.',409)
                if row['state']=='pending':
                    await w.provider_retry.cancel_for_control()
                if row['state']=='pending' and row['stage']!='native_paused':
                    self.goals.stage(w.session_id,data['requestId'],'native_pause')
                    confirmed=await self.pause(origin='user')
                    if confirmed and (not self.native or self.native['status']!='active'):
                        self.goals.stage(w.session_id,data['requestId'],'native_paused')
                    else: raise ProjectFault('The native Goal pause was not confirmed.',503)
                    if command['action']=='pause': self.goals.finish(w.session_id,data['requestId'],phase='idle' if self.idle.is_set() else 'pausing')
                result={'result':self.goals.receipt(w.session_id,data['requestId'])}
            writer.write((encode(result)+'\n').encode());await writer.drain()
            self.evaluate_later()
        except Exception as error:
            writer.write((encode({'error':str(error) if isinstance(error,ProjectFault) else 'The original worker control could not be confirmed.','code':getattr(error,'code',503)})+'\n').encode())
            try: await writer.drain()
            except Exception: pass
        finally:
            self.handlers.discard(handler)
            self.clients.discard(writer);writer.close()
            try: await writer.wait_closed()
            except Exception: pass

    async def live_command(self,rid,row,command):
        w=self.worker
        if row['state']!='pending': return
        selection=command['target']
        if (selection['runId']!=w.run_id or selection['threadId']!=w.thread_id
                or w.stopping or w.done.is_set() or self.closed):
            self.goals.finish(w.session_id,rid,'failed','The original live run ended or is stopping. Preserve the draft.')
            return
        # Once a native mutation has been submitted, a repeated delivery may
        # only read its original receipt. Recovery never repeats the mutation.
        if row['stage']!='accepted': return
        with w.store.db:
            claimed=w.store.db.execute("UPDATE goal_commands SET stage='worker_received' WHERE request_id=? AND state='pending' AND stage='accepted'",(rid,)).rowcount
        if not claimed:return
        from goal_live import LiveGoals
        from goal_contract import save_params
        from goal_control import matches
        try:
            if command['action']!='play':
                await w.provider_retry.cancel_for_control()
            value=await self.read()
            if command['action']=='play':
                proof=LiveGoals(w.store).evidence(w.session_id,rid)
                if self.clock.state=='running' and not self.idle.is_set():
                    raise ProjectFault('The previous Goal turn is still pausing. Wait for its confirmed end before Play.',409)
                if not value or value['objective']!=proof['goal']['objective'] or value['status'] in ('active','usageLimited','budgetLimited','complete'):
                    raise ProjectFault('The saved Goal changed, is already active or reached its limit. Review it before Play.',409)
                self.activating=True;self.dormant=False;self.armed=True
                self.activation={**proof['goal'],'requestId':rid}
                method,params='thread/goal/set',{'threadId':w.thread_id,'status':'active','origin':'user'}
            elif command['action']=='save':
                if value and value['status']=='active': raise ProjectFault('Pause the active Goal before changing its text.',409)
                method,params=save_params(w.thread_id,command['objective'],value)
            else:
                if not value:
                    self.goals.finish(w.session_id,rid);return
                method,params='thread/goal/set',{'threadId':w.thread_id,'status':'paused','origin':'user'}
            self.goals.stage(w.session_id,rid,'native_live_mutation')
            try: await w.client.request(method,params,timeout=10)
            except Exception: pass  # Only readback may confirm a lost reply.
            value=await self.read()
            confirmed=(value and value['objective']==self.activation['objective'] and (value['status']=='active' or self.live_active_seen and value['status']=='complete')) if command['action']=='play' else matches(command['action'],command.get('objective'),value)
            if not confirmed:
                self.goals.finish(w.session_id,rid,'unknown','The original live Goal mutation was not confirmed. It was not repeated.')
                if command['action']=='play': w.uncertain_effect=True;w.defer_stop()
            else:
                if command['action']=='play':
                    with w.store.db: w.store.db.execute("UPDATE goal_activations SET state='confirmed' WHERE request_id=?",(rid,))
                self.goals.finish(w.session_id,rid,phase='idle' if self.idle.is_set() or command['action']!='pause' else 'pausing')
        except Exception as error:
            latest=self.goals.command(w.session_id,rid)
            self.goals.finish(w.session_id,rid,'failed' if latest['stage'] in ('accepted','worker_received') else 'unknown',str(error) if isinstance(error,ProjectFault) else 'The original live command could not be confirmed. It was not repeated.')
            if command['action']=='play' and latest['stage'] not in ('accepted','worker_received'): w.uncertain_effect=True;w.defer_stop()
        finally:
            self.activating=False;self.evaluate_later()

    async def close(self):
        if self.closed:return
        self.closed=True
        await self.clock.close()
        if self.server: self.server.close();await self.server.wait_closed()
        for writer in tuple(self.clients): writer.close()
        handlers=self.handlers-{asyncio.current_task()}
        for handler in handlers: handler.cancel()
        if handlers: await asyncio.gather(*handlers,return_exceptions=True)
        for task in tuple(self.tasks): task.cancel()
        if self.tasks: await asyncio.gather(*self.tasks,return_exceptions=True)

    def finish_pending(self):
        for row in self.worker.store.db.execute("SELECT * FROM goal_commands WHERE state='pending'").fetchall():
            if json.loads(row['payload']).get('target',{}).get('runId')==self.worker.run_id:
                self.goals.finish(self.worker.session_id,row['request_id'],'failed' if row['stage'] in ('accepted','worker_received') else 'unknown',
                    'The original worker closed before this command was confirmed. Nothing was repeated.')
