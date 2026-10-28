"""Synthetic skill deletion: exact receipt, references, identity and restart."""
import asyncio
from contextlib import closing
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock,patch
import uuid
import test_skills as fixtures
from host import Host
from run_store import admit,get_run,transition
from skill_delete import preview,delete,resume,original
from skill_application import packages
from store import ProjectFault

class SkillDeleteTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.Skills.setUp
    tearDown=fixtures.Skills.tearDown
    open=fixtures.Skills.open
    settings=fixtures.Skills.settings
    input=fixtures.Skills.input
    async def host_and_input(self):
        host=Host(self.config);host.active_unit=AsyncMock(return_value=False)
        view,_=await preview(host,self.ids[0]);return host,{'requestId':str(uuid.uuid4()),'revision':view['revision'],'scopeHash':view['scopeHash'],'confirmName':view['name']}
    async def test_complete_scope_exact_replay_foreign_link_and_stale_confirmation(self):
        host,data=await self.host_and_input();target=self.skills/self.ids[0]
        foreign=self.root/'foreign';foreign.write_text('keep outside');(target/'Sessions/foreign-link').symlink_to(foreign)
        for part in ('Workspace/assets/own','Revisions/owned/Workspace','Sessions/owned/Codex','Sessions/owned/Generated'):
            path=target/part;path.mkdir(parents=True,exist_ok=True);(path/'own.txt').write_text('owned synthetic bytes')
        with self.assertRaises(ProjectFault):await delete(host,self.ids[0],{**data,'confirmName':'different'})
        with self.assertRaises(ProjectFault):await delete(host,self.ids[0],data)
        host,data=await self.host_and_input()
        accepted=await delete(host,self.ids[0],data);self.assertEqual(accepted['state'],'deleting')
        self.assertEqual(await delete(host,self.ids[0],data),accepted)
        await resume(host,data['requestId'])
        with closing(packages.connect(self.skills)) as db:self.assertEqual(original(db,data['requestId'],self.ids[0])['state'],'deleted')
        self.assertFalse(target.exists());self.assertTrue((self.skills/self.ids[1]).exists());self.assertEqual(foreign.read_text(),'keep outside')
        self.assertEqual((await delete(host,self.ids[0],data))['state'],'deleted')
        with self.assertRaises(ProjectFault):await delete(host,self.ids[0],{**data,'scopeHash':'0'*64})
    async def test_active_own_and_foreign_frozen_queue_references_block(self):
        host,data=await self.host_and_input()
        with self.open() as store:
            run,_=admit(store,self.session['id'],self.input(),self.providers)
        view,_=await preview(host,self.ids[0]);self.assertFalse(view['allowed']);self.assertEqual(view['blockers'][0]['ownerType'],'skill')
        with self.assertRaises(ProjectFault):await delete(host,self.ids[0],data)
        with self.open() as store:transition(store,run['id'],'completed')
        # A separate Skill Manager owner retains this published identity in an accepted queue.
        with self.open(self.ids[1]) as store,patch('session_store.engine',return_value=self.engine):
            session=store.create(self.settings(),self.providers)
            from message_store import Messages
            message,_=Messages(store).accept(session['id'],{'requestId':str(uuid.uuid4()),'revision':1,'mode':'queue','text':'Own queued foreign work'},self.providers)
            row=Messages(store).row(session['id'],message['requestId']);frozen=json.loads(row['frozen']);frozen['config']['skillAccess']={'entries':[{'id':self.ids[0]}]}
            with store.db:store.db.execute('UPDATE session_messages SET frozen=? WHERE request_id=?',(json.dumps(frozen),message['requestId']))
        view,_=await preview(host,self.ids[0]);self.assertFalse(view['allowed']);self.assertTrue(any(x.get('ownerId')==self.ids[1] for x in view['blockers']))
    async def test_crash_after_atomic_detach_resumes_original_and_blocks_new_owner(self):
        host,data=await self.host_and_input();await delete(host,self.ids[0],data)
        with patch('skill_delete.remove',side_effect=OSError('owned interruption')):await resume(host,data['requestId'])
        with closing(packages.connect(self.skills)) as db:self.assertEqual(original(db,data['requestId'],self.ids[0])['state'],'unknown')
        self.assertFalse((self.skills/self.ids[0]).exists())
        with self.assertRaises(ProjectFault):
            with self.open():pass
        await resume(host,data['requestId'])
        with closing(packages.connect(self.skills)) as db:self.assertEqual(original(db,data['requestId'],self.ids[0])['state'],'deleted')
    async def test_lifecycle_gate_rejects_admission_and_preserves_configuration(self):
        from skill_lifecycle import api
        host,data=await self.host_and_input()
        with self.open() as store:
            with api.lock(self.skills,True,fault=ProjectFault):
                with self.assertRaises(ProjectFault) as busy:admit(store,self.session['id'],self.input(),self.providers)
                self.assertEqual(busy.exception.code,423)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)
        from message_store import Messages
        with self.open() as store:
            Messages(store).accept(self.session['id'],{'requestId':str(uuid.uuid4()),'revision':1,'mode':'queue','text':'Own deferred admission'},self.providers)
        host.inboxes.add(('skill',self.ids[0],self.session['id']))
        with api.lock(self.skills,True,fault=ProjectFault):await host.dispatch_queues()
        with self.open() as store:self.assertFalse(Messages(store).snapshot(self.session['id'])['held'])
        with closing(packages.connect(self.skills)) as db:
            packages.rename_skill(db,self.skills,{'id':self.ids[0],'revision':1,'name':'Renamed own fixture'})
        with self.assertRaises(ProjectFault):await delete(host,self.ids[0],data)
