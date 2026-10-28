"""Historical unknown flags must carry the current, original job reconciliation."""
import copy
import hashlib
import json
import sqlite3
import uuid
import unittest
from contextlib import closing

from goal_recovery import snapshot, instructions
from run_store import admit, transition
from session_store import encode
import test_runs


class DevelopmentRecovery(unittest.TestCase):
    def setUp(self):
        self.fixture = test_runs.Runs(); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.path = self.fixture.projects / self.fixture.pid / 'Development/Development.sqlite'
        self.path.parent.mkdir()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,request_id TEXT,payload TEXT)')
            db.execute('CREATE TABLE recoveries(id TEXT PRIMARY KEY,job_id TEXT,previous TEXT,receipt TEXT)')

    def original(self, store, *, reading=False, closed_unknown=False):
        f = self.fixture
        run, _ = admit(store, f.sid, {**f.data, 'requestId': str(uuid.uuid4())}, f.providers)
        call = 'original-' + str(uuid.uuid4())
        tool = 'studio_read_development_job' if reading else 'studio_run_project'
        job_id = str(uuid.uuid4())
        request = str(uuid.uuid5(uuid.UUID(run['id']), 'development:' + call))
        recovery = {'schema': 1, 'id': str(uuid.uuid4()), 'guestEndConfirmed': True, 'replayed': False,
            'source': 'private-guest-close-receipt' if closed_unknown else 'vm-stopped'}
        job = {'id': job_id, 'kind': 'execution', 'projectId': f.pid, 'sessionId': f.sid,
            'agentRunId': run['id'], 'state': 'unknown' if closed_unknown else 'interrupted',
            'exitCode': None, 'guestState': {'closeConfirmed': True}, 'recovery': recovery}
        result = {'error': 'unknown', 'development': {'jobId': job_id, 'state': 'unknown'},
            'output': encode({'job': {**job, 'secret': 'do-not-copy-job-output'}})}
        with store.db:
            store.db.execute('INSERT INTO tools VALUES(?,?,?,?,?,?,?)',
                (run['id'], call, tool, 'hash', 'unknown', encode({'secret': 'do-not-copy-arguments'}), encode(result)))
        transition(store, run['id'], 'unknown')
        self.save(request, job)
        return run, call, request, job

    def save(self, request, job, proof=None):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM jobs'); db.execute('DELETE FROM recoveries')
            db.execute('INSERT INTO jobs VALUES(?,?,?)', (job['id'], request, encode(job)))
            recovery = job.get('recovery')
            if recovery:
                db.execute('INSERT INTO recoveries VALUES(?,?,?,?)',
                    (recovery['id'], job['id'], '{}', encode(proof if proof is not None else recovery)))

    def test_original_job_id_and_committed_end_replace_stale_warning_without_rewriting_history(self):
        f = self.fixture
        for reading in (False, True):
            with self.subTest(reading=reading), f.open() as store:
                run, call, _, job = self.original(store, reading=reading, closed_unknown=reading)
                before = tuple(store.db.execute('SELECT * FROM tools WHERE call_id=?', (call,)).fetchone())
                digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
                current = snapshot(store, f.sid)
                ref = next(v for v in current['tools'] if v['call_id'] == call)
                self.assertEqual(ref['development'], {'jobId': job['id'], 'kind': 'execution',
                    'state': job['state'], 'readOnly': reading, 'recovery': {k: job['recovery'][k]
                        for k in ('id', 'source', 'guestEndConfirmed', 'replayed')}})
                self.assertNotEqual(ref['run_id'], ref['development']['jobId'])
                text = instructions({'goalRecovery': current})
                self.assertIn('run_id identifies an agent run, never a development job', text)
                self.assertIn('continue newly authorized work without replaying the original call', text)
                self.assertNotIn('do-not-copy', text)
                self.assertEqual(tuple(store.db.execute('SELECT * FROM tools WHERE call_id=?', (call,)).fetchone()), before)
                self.assertEqual(store.db.execute('SELECT state FROM runs WHERE id=?', (run['id'],)).fetchone()[0], 'unknown')
                self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), digest)

    def test_foreign_incomplete_or_damaged_evidence_keeps_unknown_protection(self):
        f = self.fixture
        with f.open() as store:
            _, call, request, original = self.original(store)
            cases = ('project', 'session', 'run', 'kind', 'request', 'unconfirmed', 'close', 'proof', 'missing', 'malformed', 'skill')
            for case in cases:
                with self.subTest(case=case):
                    job = copy.deepcopy(original); proof = None; bound = request
                    if case in ('project', 'session', 'run'):
                        job[{'project': 'projectId', 'session': 'sessionId', 'run': 'agentRunId'}[case]] = str(uuid.uuid4())
                    elif case == 'kind': job['kind'] = 'deploy'
                    elif case == 'request': bound = str(uuid.uuid4())
                    elif case == 'unconfirmed': job['recovery']['guestEndConfirmed'] = False
                    elif case == 'close': job['guestState']['closeConfirmed'] = False
                    elif case == 'proof': proof = {**job['recovery'], 'replayed': True}
                    self.save(bound, job, proof)
                    if case == 'missing':
                        with closing(sqlite3.connect(self.path)) as db, db: db.execute('DELETE FROM recoveries')
                    elif case == 'malformed':
                        with closing(sqlite3.connect(self.path)) as db, db: db.execute("UPDATE jobs SET payload='[]'")
                    elif case == 'skill': store.owner_type = 'skill'
                    try:
                        current = snapshot(store, f.sid)
                    finally: store.owner_type = 'project'
                    ref = next(v for v in current['tools'] if v['call_id'] == call)
                    self.assertNotIn('recovery', ref.get('development', {}))
                    self.assertEqual(ref['state'], 'unknown')
            # No development database is created to fill a missing reference.
            self.path.rename(self.path.with_suffix('.saved'))
            self.assertNotIn('development', snapshot(store, f.sid)['tools'][0])
            self.assertFalse(self.path.exists())


if __name__ == '__main__': unittest.main()
