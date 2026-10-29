"""Isolated activity projections; no agent, model, systemd unit or VM starts."""
import asyncio
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import uuid

from attachment_store import birth
from project_activity import snapshot, connect, UNIT
from store import ProjectFault


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.workers = self.root / 'workers'; self.workers.mkdir()
        self.projects = [str(uuid.uuid4()) for _ in range(3)]
        with closing(sqlite3.connect(self.root / 'Projects.sqlite')) as db, db:
            db.execute('PRAGMA user_version=1'); db.execute('CREATE TABLE projects(id TEXT PRIMARY KEY,state TEXT)')
            db.executemany("INSERT INTO projects VALUES (?,'ready')", [(p,) for p in self.projects])
        self.host = SimpleNamespace(config={'projects':str(self.root),'uid':os.geteuid()}, root=self.workers, active={},
            metadata=lambda path: json.loads(path.read_text()))
        self.current = {}; self.calls = []

    def add(self, project=None, state='running', goal=False, kind='project'):
        project = project or self.projects[0]; run = str(uuid.uuid4()); sid = str(uuid.uuid4())
        meta = {'runId':run,'sessionId':sid,'ownerType':kind,'ownerId':project,'release':'fixture-release'}
        path = self.workers / run; path.mkdir(); (path / 'worker.json').write_text(json.dumps(meta))
        self.host.active[run] = meta
        path = self.root / project / 'Sessions'; path.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path / 'Sessions.sqlite')) as db, db:
            db.execute('PRAGMA user_version=1')
            db.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,project_id TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,session_id TEXT,state TEXT,busy INTEGER,worker TEXT,config TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS session_goals(session_id TEXT PRIMARY KEY,run_id TEXT,native TEXT,phase TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS goal_turns(run_id TEXT,turn_id TEXT,status TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS goal_activations(run_id TEXT,session_id TEXT,state TEXT)')
            worker = {'pid':os.getpid(),'birth':birth(os.getpid()),'release':meta['release']}
            db.execute('INSERT INTO sessions VALUES (?,?)', (sid,project))
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?)', (run,sid,state,1,json.dumps(worker),json.dumps({'goalExecution':{'requestId':str(uuid.uuid4())}} if goal else {})))
            db.execute('INSERT INTO session_goals VALUES (?,?,?,?)', (sid,run,json.dumps({'status':'paused'}),'idle'))
        self.current[UNIT.format(run)] = {'ActiveState':'active','MainPID':str(os.getpid())}
        return run, sid, path / 'Sessions.sqlite'

    async def units(self, names):
        self.calls.append(names); return {name:self.current[name] for name in names if name in self.current}

    async def active(self): return (await snapshot(self.host,self.units))['activeProjectIds']

    def update(self, path, query, args=()):
        with closing(sqlite3.connect(path)) as db, db: db.execute(query,args)

    async def test_or_lifecycle_and_one_batched_unit_read(self):
        first, _, path = self.add(); second, _, _ = self.add(); third, _, other = self.add(self.projects[1],state='starting')
        self.assertEqual(set(await self.active()),set(self.projects[:2])); self.assertEqual(len(self.calls[-1]),3)
        self.update(path,"UPDATE runs SET state='completed',busy=0 WHERE id=?",(first,))
        self.assertEqual(set(await self.active()),set(self.projects[:2]))
        self.update(path,"UPDATE runs SET state='stopping' WHERE id=?",(second,))
        self.assertIn(self.projects[0],await self.active())
        self.current[UNIT.format(second)]['ActiveState']='inactive'
        self.assertEqual(await self.active(),[self.projects[1]])
        self.update(other,"UPDATE runs SET state='interrupted',busy=0 WHERE id=?",(third,))
        self.assertEqual(await self.active(),[])

    async def test_queue_unknown_foreign_owner_and_absent_units_are_inactive(self):
        self.add(state='queued'); self.add(state='unknown'); self.add(self.projects[1],kind='skill')
        self.add(str(uuid.uuid4())); run,_,_=self.add(self.projects[2]); self.current.pop(UNIT.format(run))
        self.assertEqual(await self.active(),[])
        self.assertEqual(len(self.calls[-1]),1)

    async def test_goal_paused_idle_vs_actual_turn_and_normal_run(self):
        run,sid,path=self.add(goal=True)
        self.assertEqual(await self.active(),[])
        self.update(path,"UPDATE session_goals SET native=?",(json.dumps({'status':'active'}),))
        self.assertEqual(await self.active(),[self.projects[0]])
        self.update(path,"UPDATE session_goals SET phase='unknown'")
        self.assertEqual(await self.active(),[])
        self.update(path,"UPDATE session_goals SET native=?,phase='idle'",(json.dumps({'status':'paused'}),))
        self.update(path,"INSERT INTO goal_turns VALUES (?,'turn','running')",(run,))
        self.assertEqual(await self.active(),[self.projects[0]])
        self.update(path,"UPDATE goal_turns SET status='completed'")
        self.assertEqual(await self.active(),[])
        self.update(path,"UPDATE runs SET config='{}'")
        self.assertEqual(await self.active(),[self.projects[0]])
        self.update(path,"INSERT INTO goal_activations VALUES (?,?,'confirmed')",(run,sid))
        self.assertEqual(await self.active(),[])

    async def test_worker_pid_birth_uid_release_manifest_and_session_binding(self):
        run,_,path=self.add(); original=self.current[UNIT.format(run)].copy()
        self.current[UNIT.format(run)]['MainPID']='1'; self.assertEqual(await self.active(),[])
        self.current[UNIT.format(run)]=original
        self.host.config['uid']=-1; self.assertEqual(await self.active(),[]); self.host.config['uid']=os.geteuid()
        for key,value in [('birth','wrong'),('release','wrong')]:
            worker={'pid':os.getpid(),'birth':birth(os.getpid()),'release':'fixture-release'};worker[key]=value
            self.update(path,'UPDATE runs SET worker=?',(json.dumps(worker),)); self.assertEqual(await self.active(),[])
        self.update(path,'UPDATE runs SET worker=?',(json.dumps({'pid':os.getpid(),'birth':birth(os.getpid()),'release':'fixture-release'}),))
        self.update(path,"UPDATE sessions SET project_id='foreign'"); self.assertEqual(await self.active(),[])
        self.update(path,'UPDATE sessions SET project_id=?',(self.projects[0],))
        record=self.workers/run/'worker.json';raw=record.read_text();record.write_text('{}')
        self.assertEqual(await self.active(),[]);record.write_text(raw)
        self.assertEqual(await self.active(),[self.projects[0]])

    async def test_read_only_projection_and_unavailable_source(self):
        self.add()
        def hashes():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        before=hashes();await self.active();self.assertEqual(before,hashes())
        with closing(connect(self.root/'Projects.sqlite')) as db:
            with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM projects')
        async def unavailable(_):raise asyncio.TimeoutError()
        with self.assertRaises(ProjectFault):await snapshot(self.host,unavailable)
        (self.root/'Projects.sqlite').rename(self.root/'original.sqlite')
        (self.root/'Projects.sqlite').symlink_to(self.root/'original.sqlite')
        with self.assertRaises(ProjectFault):await self.active()


if __name__ == '__main__': unittest.main()
