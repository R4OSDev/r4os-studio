"""Stored synthetic captures only: no VM, QMP, inference or new guest action."""
import base64
import hashlib
import json
from types import SimpleNamespace
import unittest
import uuid

import test_runs as fixtures
from evidence import publish
from jobs import Jobs
from run_store import admit
from screenshot_gallery import page,member
from session_store import encode
from store import ProjectFault

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7wAAAABJRU5ErkJggg==')


class ScreenshotGallery(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.Runs('test_concurrent_retry_snapshot_stop_and_replay');self.f.setUp();self.addCleanup(self.f.tearDown)
        self.s=self.enterContext(self.f.open());self.run,_=admit(self.s,self.f.sid,self.f.data,self.f.providers)
        self.jobs=Jobs(self.f.projects,self.f.r4os,self.f.pid);self.addCleanup(self.jobs.close)
        self.sequence=0

    def job(self):
        job,_=self.jobs.admit('build',{'requestId':str(uuid.uuid4()),'projectRevision':1,'settingsRevision':1},owner={'sessionId':self.f.sid,'agentRunId':self.run['id']})
        return self.jobs.update(job['id'],'completed')

    def capture(self,job,legacy=None,tool='studio_capture_vm'):
        self.sequence+=1;call='owned-capture-'+str(self.sequence);request=str(uuid.uuid5(uuid.UUID(self.run['id']),'development:'+call))
        arguments={'jobId':job['id'],**({'observeAfterStep':1} if tool=='studio_send_vm_input' else {})}
        with self.s.db:self.s.db.execute('INSERT INTO tools VALUES (?,?,?,?,?,?,NULL)',(self.run['id'],call,tool,'own-hash','intent',encode(arguments)))
        image=publish(self.jobs,job,'screenshot',PNG,width=1,height=1,observer={'sessionId':self.f.sid,'agentRunId':self.run['id'],'model':'owned'},
            source='qmp-png',scope='assigned-vm-screen',captureOrigin=None if legacy else {'requestId':request,'operation':'capture' if tool=='studio_capture_vm' else 'input'})
        if legacy=='tool':
            with self.s.db:self.s.db.execute('UPDATE tools SET state=\'completed\',result=? WHERE run_id=? AND call_id=?',(encode({'success':True,'image':image}),self.run['id'],call))
        if legacy=='action':self.action(job,request,image)
        return image,request,call

    def action(self,job,request,image):
        with self.jobs.db:
            self.jobs.db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,result TEXT)')
            self.jobs.db.execute('INSERT INTO actions VALUES (?,?,?,?,?)',(request,job['id'],'owned','completed',encode({'evidenceId':image['id']})))

    def test_all_jobs_and_images_stable_pages_identical_frames_and_cursor_scope(self):
        ids=[];first=self.job()
        for _ in range(40):ids.append(self.capture(first)[0]['id'])
        for _ in range(101):ids.append(self.capture(self.job())[0]['id'])
        source=self.jobs.root/'Development.sqlite';before=hashlib.sha256(source.read_bytes()).hexdigest()
        result=page(self.s,self.f.sid);self.assertTrue(result['coverage']['complete']);self.assertEqual(result['coverage']['unqualified'],0)
        self.assertEqual(len(result['items']),32);old=result['nextCursor'];seen=[i['id'] for i in result['items']]
        newest=self.capture(self.job())[0]['id']
        while result['nextCursor']:
            result=page(self.s,self.f.sid,result['nextCursor']);seen.extend(i['id'] for i in result['items'])
        self.assertEqual(seen,ids[::-1]);self.assertEqual(len(seen),len(set(seen)));self.assertNotIn(newest,seen)
        self.assertEqual(page(self.s,self.f.sid)['items'][0]['id'],newest)
        with self.assertRaises(ProjectFault):page(self.s,self.f.sid,old[:-1]+('0' if old[-1]!='0' else '1'))
        foreign=str(uuid.uuid4())
        with self.s.db:self.s.db.execute("INSERT INTO sessions SELECT ?,project_id,'Other',settings,engine,NULL,1,created_at,updated_at FROM sessions WHERE id=?",(foreign,self.f.sid))
        with self.assertRaises(ProjectFault):page(self.s,foreign,old)
        self.assertEqual(page(self.s,foreign)['items'],[])
        self.assertEqual(member(self.s,self.f.sid,first['id'],ids[0])['sha256'],hashlib.sha256(PNG).hexdigest())
        with self.assertRaises(ProjectFault):member(self.s,foreign,first['id'],ids[0])
        # A separate registration is preserved even when bytes are identical.
        self.assertEqual(len({i['sha256'] for i in page(self.s,self.f.sid)['items']}),1)
        after_new=hashlib.sha256(source.read_bytes()).hexdigest();page(self.s,self.f.sid)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),after_new);self.assertNotEqual(before,after_new)

    def test_legacy_original_receipts_lost_reply_gaps_and_later_resolution(self):
        job=self.job();tool=self.capture(job,'tool')[0];action=self.capture(job,'action')[0]
        lost,request,call=self.capture(job,'lost')
        direct,_,_=self.capture(job)
        intermediate,_,_=self.capture(job,tool='studio_send_vm_input')
        manual=publish(self.jobs,job,'screenshot',PNG,width=1,height=1,source='qmp-png',scope='assigned-vm-screen',observer=None)
        foreign=publish(self.jobs,job,'screenshot',PNG,width=1,height=1,source='qmp-png',scope='assigned-vm-screen',observer={'sessionId':str(uuid.uuid4()),'agentRunId':self.run['id']})
        publish(self.jobs,job,'file',b'owned upload')
        result=page(self.s,self.f.sid);listed={i['id'] for i in result['items']}
        self.assertEqual(listed,{tool['id'],action['id'],direct['id'],intermediate['id']});self.assertEqual(result['coverage']['unqualified'],1)
        self.assertNotIn(manual['id'],listed);self.assertNotIn(foreign['id'],listed)
        self.action(job,request,lost)
        result=page(self.s,self.f.sid);self.assertIn(lost['id'],{i['id'] for i in result['items']});self.assertEqual(result['coverage']['unqualified'],0)
        # Listing a published image never declares the original tool successful.
        self.assertEqual(self.s.db.execute('SELECT state FROM tools WHERE run_id=? AND call_id=?',(self.run['id'],call)).fetchone()[0],'intent')
        self.assertEqual(len(list(self.jobs.root.glob('Evidence/*/*.png'))),7)
        from session_delete import selections
        self.assertTrue({'gallery_state','gallery_entries','gallery_gaps'}<={v[0] for v in selections(self.s.db,self.f.sid)})

    def test_bounded_backfill_replacement_and_skill_unavailability(self):
        for _ in range(3):
            job=self.job()
            for _ in range(100):self.capture(job)
        first=page(self.s,self.f.sid);self.assertFalse(first['coverage']['complete']);self.assertEqual(first['watermark'],256)
        second=page(self.s,self.f.sid);self.assertTrue(second['coverage']['complete']);self.assertEqual(second['watermark'],300)
        # Replaced source storage expires old signed cursors and rebuilds only
        # derived references; original PNGs and source rows remain untouched.
        source=self.jobs.root/'Development.sqlite';self.jobs.close()
        replacement=source.with_suffix('.owned-replacement');replacement.write_bytes(source.read_bytes());replacement.replace(source)
        old=second['nextCursor']
        with self.assertRaises(ProjectFault):page(self.s,self.f.sid,old)
        self.jobs=Jobs(self.f.projects,self.f.r4os,self.f.pid);self.addCleanup(self.jobs.close)
        skill=SimpleNamespace(owner_type='skill',owner_id=str(uuid.uuid4()),row=lambda sid:None)
        result=page(skill,str(uuid.uuid4()));self.assertFalse(result['available']);self.assertEqual(result['items'],[])
