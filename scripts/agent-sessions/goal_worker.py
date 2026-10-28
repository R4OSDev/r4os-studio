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
    def __init__(self, worker):
        self.worker=worker;self.goals=Goals(worker.store);self.idle=asyncio.Event();self.idle.set()
        self.native=None;self.server=None;self.lock=asyncio.Lock();self.tasks=set();self.clients=set();self.activating=True
        self.evaluator=None;self.closed=False;self.last_turn_status=None
        self.generation=0
        self.armed=False;self.completed_once=False
        self.stop_reconcile=None
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
        return value

    async def before_resume(self):
        w=self.worker
        # Read/neutralize saved active state while the native thread is unloaded.
        # Resume must not authorize any implicit old work before this Play.
        value=await self.read()
        if value and value['status']=='active':
            await w.client.request('thread/goal/set',{'threadId':w.thread_id,'status':'paused','origin':'automatic'})
            value=await self.read()
        if not value or value['objective']!=w.config['goalExecution']['objective'] or value['status']=='active':
            raise ProjectFault('The saved Goal changed before its worker started.',409)

    async def activate(self):
        w=self.worker;rid=w.config['goalExecution']['requestId']
        self.server=await asyncio.start_unix_server(self.control,path='\0r4os-studio-goal-'+w.run_id,limit=2049)
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
        value=await self.read()
        if not self.idle.is_set(): return
        if value is None or value['status']!='active':
            w=self.worker
            if w.uncertain_effect: w.outcome='unknown'
            elif w.stopping or self.last_turn_status=='interrupted': w.outcome='interrupted'
            elif self.last_turn_status=='failed': w.outcome='failed';w.error=w.error or 'The native Goal turn failed.'
            else: w.outcome='completed'
            # Run completion only means this accepted execution ended. Native
            # Goal status remains paused/blocked/limited/complete as reported.
            self.goals.observe(w.session_id,w.thread_id,value,w.run_id,phase='unknown' if w.uncertain_effect else 'idle')
            w.done.set()

    async def notify(self, method, params):
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
            self.goals.observe(w.session_id,w.thread_id,self.native,w.run_id)
            if self.armed and self.native:
                changed=self.native['objective']!=w.config['goalExecution']['objective']
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
            if w.stopping and not self.closed:
                task=asyncio.create_task(w.stop());self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        elif method=='turn/completed':
            turn=params['turn'];w.turn_id=turn['id'];self.idle.set()
            self.last_turn_status=turn['status']
            with w.store.db: w.store.db.execute('INSERT INTO goal_turns VALUES (?,?,?) ON CONFLICT(run_id,turn_id) DO UPDATE SET status=excluded.status',
                (w.run_id,turn['id'],turn['status']))
            from run_store import event
            event(w.store,w.session_id,w.run_id,'nativeTurn',{'id':turn['id'],'status':turn['status']})
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
                if command['action']=='play': raise ProjectFault('This worker cannot accept another Play.',409)
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
            self.clients.discard(writer);writer.close()
            try: await writer.wait_closed()
            except Exception: pass

    async def close(self):
        self.closed=True
        if self.server: self.server.close();await self.server.wait_closed()
        for writer in tuple(self.clients): writer.close()
        for task in tuple(self.tasks): task.cancel()
        if self.tasks: await asyncio.gather(*self.tasks,return_exceptions=True)
