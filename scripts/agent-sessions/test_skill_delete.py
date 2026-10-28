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

    async def test_builtin_tombstone_survives_catalog_copy_reopen_and_changed_bundle_identity(self):
        import importlib.util,shutil
        from skill_application import catalog
        spec=importlib.util.spec_from_file_location('owned_builtin',Path(__file__).resolve().parents[1]/'skills/builtin.py');builtin=importlib.util.module_from_spec(spec);spec.loader.exec_module(builtin)
        with closing(packages.connect(self.skills)) as db:
            result=builtin.ensure(db,self.skills,'/usr/bin/node',packages);ident=result['skillId']
        old=self.root/'old-catalog.sqlite';shutil.copy2(self.skills/'Skills.sqlite',old)
        host=Host(self.config);host.active_unit=AsyncMock(return_value=False);view,_=await preview(host,ident)
        data={'requestId':str(uuid.uuid4()),'revision':view['revision'],'scopeHash':view['scopeHash'],'confirmName':view['name']}
        await delete(host,ident,data);await resume(host,data['requestId'])
        with closing(packages.connect(self.skills)) as db:self.assertTrue(builtin.ensure(db,self.skills,'/usr/bin/node',packages)['deleted'])
        shutil.copy2(old,self.skills/'Skills.sqlite')
        with closing(packages.connect(self.skills)) as db:self.assertTrue(builtin.ensure(db,self.skills,'/usr/bin/node',packages)['deleted'])
        self.assertNotIn(ident,[entry['id'] for entry in catalog(self.projects)]);self.assertFalse((self.skills/ident).exists())
        base=self.root/'changed-bundle';shutil.copytree(builtin.BASE,base);manifest=base/(builtin.SOURCE+'.json');value=json.loads(manifest.read_text());value['id']=str(uuid.uuid4());manifest.write_text(json.dumps(value))
        with closing(packages.connect(self.skills)) as db:self.assertTrue(builtin.ensure(db,self.skills,'/usr/bin/node',packages,base)['deleted'])
        self.assertFalse((self.skills/value['id']).exists())

    async def test_published_foreign_run_blocks_then_history_and_copied_source_survive(self):
        from skill_application import revision,catalog
        from session_store import encode
        with closing(packages.connect(self.skills)) as db:
            current=packages.detail(db,self.skills,self.ids[0]);path=self.skills/self.ids[0]/'Workspace/SKILL.md';packages.atomic(path,b'---\nname: owned-published\ndescription: Owned synthetic published resource.\n---\n\nOwned instruction.\n')
            current=packages.detail(db,self.skills,self.ids[0]);packages.publish(db,self.skills,{'id':self.ids[0],'revision':current['skill']['revision'],'draftHash':current['draftHash'],'requestId':str(uuid.uuid4())},'/usr/bin/node')
        entry=next(v for v in catalog(self.projects) if v['id']==self.ids[0]);copy=self.root/'project-copy.md';copy.write_bytes(path.read_bytes())
        with self.open(self.ids[1]) as store,patch('session_store.engine',return_value=self.engine):
            session=store.create(self.settings(),self.providers)
            run,_=admit(store,session['id'],{'requestId':str(uuid.uuid4()),'revision':1,'text':'Owned published resource use','skillSelection':1,'skillScripts':1},self.providers)
            original_config=get_run(store,run['id'])['config']
        host,data=await self.host_and_input();view,_=await preview(host,self.ids[0]);self.assertFalse(view['allowed'])
        with self.open(self.ids[1]) as store:transition(store,run['id'],'completed')
        host,data=await self.host_and_input();await delete(host,self.ids[0],data);await resume(host,data['requestId'])
        with self.open(self.ids[1]) as store:self.assertEqual(get_run(store,run['id'])['config'],original_config)
        self.assertIn(b'Owned instruction.',copy.read_bytes())
        with self.assertRaises(ProjectFault):revision(self.projects,entry)

    async def test_own_statistics_preferences_and_attributed_finished_runtime_are_retained_or_cleaned(self):
        from stats_store import Source,read
        from session_store import encode
        with self.open() as store:
            Source(store).put(self.session['id'],'tokens',{'ownedResponse':'skill-delete'},{'total':17});Source(store).put(self.session['id'],'goal',{'ownedPlay':'skill-delete'},{'durationMs':1234,'uncertain':False});Source(store).flush()
            run,_=admit(store,self.session['id'],self.input(),self.providers);transition(store,run['id'],'completed')
        preferences=self.skills/'SessionSettings.sqlite'
        with closing(__import__('sqlite3').connect(preferences)) as db,db:
            db.execute('CREATE TABLE overrides(owner_type TEXT,owner_id TEXT,session_id TEXT,choices TEXT,PRIMARY KEY(owner_type,owner_id,session_id))');db.execute('PRAGMA user_version=1')
            db.execute('INSERT INTO overrides VALUES (?,?,?,?)',('skill',self.ids[0],self.session['id'],encode({self.ids[1]:False})))
            db.execute('INSERT INTO overrides VALUES (?,?,?,?)',('skill',self.ids[1],'other-session',encode({self.ids[0]:False,self.ids[1]:False})))
        host=Host(self.config);host.active_unit=AsyncMock(return_value=False);runtime=self.root/'owned-runtime';host.config['agentRuntime']=str(runtime)
        metadata={'ownerType':'skill','ownerId':self.ids[0],'sessionId':self.session['id'],'runId':run['id']}
        record=host.root/run['id'];record.mkdir();(record/'worker.json').write_text(json.dumps(metadata));(runtime/run['id']).mkdir(parents=True);(runtime/run['id']/'own').write_text('own')
        foreign=runtime/str(uuid.uuid4());foreign.mkdir();(foreign/'keep').write_text('foreign')
        with patch.object(host,'metadata',return_value=metadata):
            view,_=await preview(host,self.ids[0]);data={'requestId':str(uuid.uuid4()),'revision':view['revision'],'scopeHash':view['scopeHash'],'confirmName':view['name']};await delete(host,self.ids[0],data);await resume(host,data['requestId'])
        self.assertFalse(record.exists());self.assertFalse((runtime/run['id']).exists());self.assertEqual((foreign/'keep').read_text(),'foreign')
        self.assertEqual(read(self.projects)['tokens']['total'],'17');self.assertEqual(read(self.projects)['longestGoalMs'],1234)
        with closing(__import__('sqlite3').connect(preferences)) as db:
            rows=db.execute('SELECT owner_id,choices FROM overrides').fetchall();self.assertEqual(rows,[(self.ids[1],encode({self.ids[1]:False}))])
