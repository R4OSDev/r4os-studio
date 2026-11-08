"""Accepted originals, real readonly namespaces and unchanged legacy captures."""
from contextlib import closing
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch
import uuid

from PIL import Image
from attachment_files import FIELD, mounts, instructions
from attachment_store import Attachments
from image_inputs import namespace
from owner import open_lock
from profile import PROFILE, NOTES_SKILL_PROFILE, CODEX_VERSION, CODEX_SHA256, permission_tools
from run_store import admit, capture_input, transition
from session_store import SessionStore, encode
from skill_application import packages
from store import ProjectFault
from test_document_inputs import pdf
import test_runs as fixtures
from worker import Worker


class AttachmentFiles(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def configure(self, store, sid, profile=PROFILE):
        with store.db:
            settings=json.loads(store.row(sid)['settings'])
            settings['permissions']={'studio.'+name:True for name in permission_tools(profile)}
            store.db.execute('UPDATE sessions SET settings=?,engine=? WHERE id=?',
                (encode(settings),encode({'profile':profile,'version':CODEX_VERSION,'sha256':CODEX_SHA256}),sid))

    def png(self):
        stream=io.BytesIO();Image.new('P',(32,32),1).save(stream,'PNG');return stream.getvalue()

    def upload(self, store, sid, raw, name):
        result=Attachments(store,sid).upload({'requestId':str(uuid.uuid4()),'name':name,
            'mediaType':'application/octet-stream','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},io.BytesIO(raw))
        self.assertEqual(result['state'],'ready',result);return result['attachment']

    def message(self, ids=()):
        return {'requestId':str(uuid.uuid4()),'revision':1,'text':'Use the requested original asset.',
                'attachments':list(ids),'nativeImageInputs':1,'documentInputs':1}

    def worker(self, run, owner=None, kind='project'):
        actual=Path(__file__).resolve().parents[2]/'Data/R4OS'
        if not (actual/'Toolchains/Codex'/CODEX_VERSION/'codex').is_file():self.fail('Qualified patch runtime is required.')
        worker=Worker({'projects':str(self.projects),'r4os':str(actual),'providers':str(self.providers),
                       'ownerType':kind,'ownerId':owner or self.pid,'runId':run['id']})
        worker.lease=open_lock(self.projects,kind,owner or self.pid)
        fcntl.flock(worker.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        transition(worker.store,run['id'],'running')
        return worker

    async def finish(self, worker):
        try:await worker.cleanup();transition(worker.store,worker.run_id,'completed')
        finally:
            if worker.lease is not None and not worker.lease.closed:worker.lease.close()
            worker.store.close()


    async def test_changed_foreign_unaccepted_and_revoked_files_fail_before_any_command(self):
        with self.open() as store:
            self.configure(store,self.sid);sent=self.upload(store,self.sid,self.png(),'sent.png')
            unsent=self.upload(store,self.sid,self.png(),'unsent.png')
            run,_=admit(store,self.sid,self.message([sent['id']]),self.providers)
        worker=self.worker(run)
        try:
            self.assertEqual(len(mounts(worker)),1);original=copy.deepcopy(worker.config)
            for entry in (unsent,{**sent,'sessionId':str(uuid.uuid4())}):
                worker.config[FIELD]['files']=[entry]
                with self.assertRaises(ProjectFault):mounts(worker)
            worker.config=copy.deepcopy(original)
            for right in ('studio.exec_command','studio.read_attachment','studio.read_file'):
                worker.config['permissions'][right]=False
                with self.assertRaises(ProjectFault):mounts(worker)
                worker.config=copy.deepcopy(original)
            source=Path(mounts(worker)[0][0]);raw=source.read_bytes();source.write_bytes(raw+b'changed')
            with self.assertRaises(ProjectFault):mounts(worker)
            source.write_bytes(raw);worker.lease.close()
            with self.assertRaises(ProjectFault):mounts(worker)
            worker.config.pop(FIELD);self.assertEqual(mounts(worker),[])
        finally:await self.finish(worker)

    async def test_followup_uses_sent_history_and_old_or_new_queues_never_gain_later_files(self):
        with self.open() as store:
            self.configure(store,self.sid);first=self.upload(store,self.sid,self.png(),'first.png')
            run,_=admit(store,self.sid,self.message([first['id']]),self.providers);transition(store,run['id'],'completed')
            later=self.upload(store,self.sid,self.png(),'later.png');message=self.message()
            frozen,_,_=capture_input(store,self.sid,message,self.providers)
            self.assertEqual([v['id'] for v in frozen[FIELD]['files']],[first['id']])
            legacy=copy.deepcopy(frozen);legacy.pop(FIELD)
            run,_=admit(store,self.sid,self.message([later['id']]),self.providers);transition(store,run['id'],'completed')
            current,_,_=capture_input(store,self.sid,message,self.providers,original=frozen)
            self.assertEqual(current,frozen)
            old,_,_=capture_input(store,self.sid,message,self.providers,original=legacy)
            self.assertEqual(old,legacy);self.assertNotIn(FIELD,old)
            self.assertEqual(instructions(old),'')
            invalid=copy.deepcopy(frozen);invalid[FIELD]['version']=True
            with self.assertRaises(ProjectFault):capture_input(store,self.sid,message,self.providers,original=invalid)


if __name__=='__main__':unittest.main()
