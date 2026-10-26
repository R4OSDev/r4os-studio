"""Real inherited descriptors, active-run authorization and sandboxed commits; no inference/network."""
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct
import subprocess
import time
import unittest
from unittest.mock import patch
import uuid
import test_git as fixtures
from agent import AgentLease, process
from common import ProjectFault, save
from host import Coordinator
from operations import Operations
from project_use import acquire


class AgentGitTests(unittest.TestCase):
    setUp = fixtures.GitTests.setUp
    tearDown = fixtures.GitTests.tearDown
    job = fixtures.GitTests.job

    def test_active_run_fd_handover_pushes_without_self_deadlock_and_keeps_disabled_rights_closed(self):
        action = Operations(self.config, self.job()); action.initialize()
        action.job.update(state='completed', phase='complete', result={'initialized': True}); save(self.jobs / action.job['id'] / 'job.json', action.job)
        repo = {'id': 11, 'owner': 'octocat', 'name': 'own-qa', 'fullName': 'octocat/own-qa', 'archived': False}
        bound = {'schema': 1, 'revision': 1, 'connectionId': str(uuid.uuid4()), 'userId': 7, 'repository': repo, 'branch': 'main', 'author': {'name': 'Own QA', 'email': 'qa@example.invalid'}}
        save(action.base / 'binding.json', bound)
        session, run = str(uuid.uuid4()), str(uuid.uuid4())
        config = {'owner': {'type': 'project', 'id': self.identity}, 'engine': {'profile': 'studio-tools-v6'}, 'permissions': {'studio.push_project': True}, 'revision': 1, 'projectPins': {}}
        directory = self.projects / self.identity / 'Sessions'; directory.mkdir()
        db_path = directory / 'Sessions.sqlite'
        with closing(sqlite3.connect(db_path)) as db:
            db.execute('CREATE TABLE sessions(id TEXT,project_id TEXT,revision INTEGER)')
            db.execute('CREATE TABLE runs(id TEXT,session_id TEXT,state TEXT,busy INTEGER,config TEXT,worker TEXT)')
            db.execute('INSERT INTO sessions VALUES (?,?,1)', (session, self.identity))
            db.execute('INSERT INTO runs VALUES (?,?,?,1,?,?)', (run, session, 'running', json.dumps(config), json.dumps({'pid': os.getpid(), 'birth': process(os.getpid())[1]}))); db.commit()
        lock = (self.projects / '.studio' / ('workspace-' + self.identity + '.lock')).open('a+b'); fcntl.flock(lock, fcntl.LOCK_EX)
        lifetime = acquire(self.projects, self.identity)
        parent, child = socket.socketpair(); helper = None; received = None; host = Coordinator(self.config, self.cfg)
        agent = {'sessionId': session, 'runId': run, 'workerPid': os.getpid(), 'workerBirth': process(os.getpid())[1], 'revision': 1, 'callId': 'own-call'}
        request = {'operation': 'agent_submit', 'projectId': self.identity, 'requestId': str(uuid.uuid4()), 'kind': 'push', 'input': {'commitMessage': 'Own inherited-lease commit'}, 'agent': agent}
        actual_popen = subprocess.Popen
        try:
            helper_code = 'import socket,struct,sys; s=socket.socket(fileno=int(sys.argv[1]));s.sendmsg([sys.argv[3].encode()],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,struct.pack("i",int(sys.argv[2])))]);s.recv(1)'
            helper = actual_popen(['/usr/bin/python3', '-B', '-c', helper_code, str(child.fileno()), str(lock.fileno()), json.dumps(request)], pass_fds=(child.fileno(), lock.fileno()))
            raw, controls, _, _ = parent.recvmsg(65536, socket.CMSG_SPACE(4)); received = struct.unpack('i', controls[0][2])[0]
            self.assertEqual(json.loads(raw), request)
            AgentLease(self.config, self.identity, agent, received, helper.pid).verify()
            wrong = (self.projects / '.studio' / ('workspace-' + self.identity + '.lock')).open('a+b')
            try:
                with self.assertRaises(ProjectFault): AgentLease(self.config, self.identity, agent, wrong.fileno(), helper.pid).verify()
            finally: wrong.close()
            worker_code = '''import sys
sys.path.insert(0,sys.argv.pop(1))
import worker
from operations import Operations
from git import Git
from unittest.mock import patch
remote={'head':None}
class API:
 def assert_current(self):pass
def fetch(self):
 self.remote=self.bound['repository'];self.api=API();return remote['head']
original=Git.run
def run(self,*args,**kwargs):
 if args[0]=='push':remote['head']=args[-1].split(':')[0];return b'',0
 return original(self,*args,**kwargs)
with patch.object(Operations,'fetch',fetch),patch.object(Git,'run',run):worker.main()
'''
            calls = []
            def start(args, **kwargs):
                calls.append(args)
                return actual_popen(['/usr/bin/python3', '-B', '-c', worker_code, str(Path(__file__).parent), str(self.cfg), request['requestId'], str(received)], **kwargs)
            with patch.object(host, 'release', return_value=str(Path(__file__).resolve().parents[2])), patch('host.subprocess.Popen', side_effect=start):
                result = host.request(request, helper.pid, received)
                deadline = time.monotonic() + 20
                while result['state'] in ('queued', 'running') and time.monotonic() < deadline:
                    time.sleep(.05); result = host.request({'operation': 'job', 'projectId': self.identity, 'requestId': request['requestId']})
                self.assertEqual(result['state'], 'completed', result); self.assertTrue(result['result']['pushed'])
                self.assertEqual(host.request(request, helper.pid, received)['id'], result['id']); self.assertEqual(len(calls), 1)
                with self.assertRaises(ProjectFault): host.request({**request, 'input': {'commitMessage': 'Changed same ID'}}, helper.pid, received)
                with self.assertRaises(ProjectFault): host.request({**request, 'requestId': str(uuid.uuid4()), 'agent': {**agent, 'sessionId': str(uuid.uuid4())}}, helper.pid, received)
                with self.assertRaises(ProjectFault): host.request({**request, 'requestId': str(uuid.uuid4())}, helper.pid, None)
                config['permissions']['studio.push_project'] = False
                with closing(sqlite3.connect(db_path)) as db: db.execute('UPDATE runs SET config=?', (json.dumps(config),)); db.commit()
                with self.assertRaises(ProjectFault): host.request({**request, 'requestId': str(uuid.uuid4())}, helper.pid, received)
                self.assertEqual(len(calls), 1)
            self.assertEqual(action.git.text('rev-list', '--count', 'HEAD'), '1')
        finally:
            parent.close(); child.close()
            if helper: helper.terminate(); helper.wait(timeout=5)
            if received is not None: os.close(received)
            for running in host.processes.values():
                if running.poll() is None: running.kill(); running.wait(timeout=5)
            lock.close(); lifetime.close()


if __name__ == '__main__': unittest.main()
