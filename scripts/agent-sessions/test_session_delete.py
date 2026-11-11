"""Own fixtures only: scopes, lifetime races, durable cleanup and numeric retention."""
from contextlib import closing
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import test_runs as fixtures
from host import Host
from session_store import SessionStore, encode
from profile import SKILL_PROFILE
from run_store import admit, transition
from session_delete import preview, delete, inspect, resume, original, recover
from session_lifetime import acquire
from skill_application import packages
from stats_store import Source, read
from store import ProjectFault


class SessionDeleteTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.Runs.setUp
    tearDown = fixtures.Runs.tearDown
    open = fixtures.Runs.open

    def host(self):
        control=patch('session_delete.unit_states',new=AsyncMock(return_value=False));control.start();self.addCleanup(control.stop)
        host=Host({'projects':str(self.projects),'r4os':str(self.r4os),'providers':str(self.providers),'uid':os.getuid()})
        host.active_unit=AsyncMock(return_value=False)
        return host

    def add_skill(self):
        ident=str(uuid.uuid4());sid=str(uuid.uuid4())
        with closing(packages.connect(self.root/'Skills')) as db: packages.create(db,self.root/'Skills',{'id':ident,'name':'Own skill fixture'})
        with closing(SessionStore(self.projects,self.r4os,ident,'skill')) as store,store.db:
            store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')",(sid,ident,'Own skill session',encode(self.settings),encode({'profile':SKILL_PROFILE})))
        return ident,sid

    async def command(self,host,kind='project',owner=None,sid=None):
        value=await preview(host,kind,owner or self.pid,sid or self.sid)
        self.assertTrue(value['allowed'],value)
        return {'requestId':str(uuid.uuid4()),'revision':value['revision'],'scopeHash':value['scopeHash'],'confirmName':value['name']}

    async def test_both_owner_scopes_remove_private_data_preserve_sources_other_sessions_and_statistics(self):
        skill,skill_sid=self.add_skill();host=self.host()
        for kind,owner,sid in [('project',self.pid,self.sid),('skill',skill,skill_sid)]:
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                other=str(uuid.uuid4());row=store.row(sid)
                with store.db:store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')",(other,owner,'Other session',row['settings'],row['engine']))
                path=store.directory/sid; (path/'Codex/native').mkdir(parents=True)
                (path/'Codex/native/own.jsonl').write_text('private original history')
                (path/'GeneratedImages').mkdir();(path/'GeneratedImages/image.png').write_bytes(b'private fixture image')
                foreign=self.root/('outside-'+sid);foreign.write_text('preserve outside');(path/'foreign-link').symlink_to(foreign)
                Source(store).put(sid,'tokens',{'response':sid},{'total':7})
                from goal_total import mark_new
                with store.db:mark_new(store,sid)
                from usage_stats import Usage
                from attachment_store import Attachments
                from environment_notes import Notes
                from generated_images import GeneratedImages
                Usage(store,sid).schema();Attachments(store,sid).schema();Notes(store).schema();GeneratedImages(store,sid).schema()
                run_id=str(uuid.uuid4())
                with store.db:
                    store.db.execute("INSERT INTO runs VALUES (?,?,?,'hash','completed',0,'{}',NULL,'{}',NULL,'now','now')",(run_id,sid,str(uuid.uuid4())))
                    store.db.execute("INSERT INTO statistic_usage VALUES (?,?,NULL,'own-turn','raw')",('source-'+sid,sid))
                    store.db.execute("INSERT INTO session_attachments VALUES (?,?,?,'hash','{\"private\":\"private attachment metadata\"}','ready',NULL,'{}','now')",(str(uuid.uuid4()),sid,str(uuid.uuid4())))
                    store.db.execute("INSERT INTO environment_notes VALUES (?,?,'fingerprint','{\"private\":\"private note metadata\"}',1,'now',NULL)",(str(uuid.uuid4()),sid))
                    store.db.execute("INSERT INTO generated_images VALUES (?,?,?,'own-thread','image-item','{\"private\":\"private image metadata\"}','now')",(str(uuid.uuid4()),sid,run_id))
                from request_capture import capture
                capture(store,{'owner':{'type':kind,'id':owner},'sessionId':sid,'runId':run_id,
                               'requestId':str(uuid.uuid4()),'selection':{'providerId':self.provider}},
                        '{"input":"Own archived model input"}',{'protocol':'responses','model':'fixture'}, {})
                create_id=str(uuid.uuid4());payload={'name':'Retired fixture','providerId':self.provider,'model':'fixture','effort':'low','requestId':create_id}
                import hashlib
                with store.db:store.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)',(create_id,'create',hashlib.sha256(encode(payload).encode()).hexdigest(),sid,encode({'private':'create response'})))
                other_before=tuple(store.row(other));workspace=store.workspace/'module.R4MF'
                if not workspace.exists():workspace.write_text('Own skill source')
                source_before=workspace.read_bytes()
            data=await self.command(host,kind,owner,sid)
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store,store.db:
                store.db.execute('UPDATE studio_request_bodies SET compressed=? WHERE session_id=?',(b'updated binary body',sid))
            self.assertEqual((await delete(host,kind,owner,sid,data))['state'],'deleting')
            await resume(host,kind,owner,sid,data['requestId'])
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                final=original(store,sid,data['requestId']);self.assertEqual(final['state'],'deleted');self.assertEqual(final['creationRequestIds'],[create_id])
                self.assertEqual(tuple(store.row(other)),other_before);self.assertFalse((store.directory/sid).exists())
                with self.assertRaises(ProjectFault) as gone:store.get(sid)
                self.assertEqual(gone.exception.code,410)
                with self.assertRaises(ProjectFault) as retired:store.create(payload,self.providers)
                self.assertEqual(retired.exception.code,410)
                self.assertNotIn('private original history','\n'.join(store.db.iterdump()));self.assertNotIn('create response','\n'.join(store.db.iterdump()))
                for private in ('private attachment metadata','private note metadata','private image metadata','own-turn'):
                    self.assertNotIn(private,'\n'.join(store.db.iterdump()))
                self.assertIsNone(store.db.execute('SELECT 1 FROM goal_time_coverage WHERE session_id=?',(sid,)).fetchone())
                self.assertIsNone(store.db.execute('SELECT 1 FROM studio_request_bodies WHERE session_id=?',(sid,)).fetchone())
                self.assertIsNone(store.db.execute('SELECT 1 FROM studio_requests WHERE session_id=?',(sid,)).fetchone())
                self.assertEqual(workspace.read_bytes(),source_before);self.assertEqual(foreign.read_text(),'preserve outside')
            self.assertEqual(await delete(host,kind,owner,sid,data),final)
            self.assertEqual(read(self.projects)['tokens']['total'], '7' if kind=='project' else '14')

    async def test_original_request_recovery_after_detach_and_unknown_response(self):
        host=self.host()
        with self.open() as store:
            path=store.directory/self.sid;path.mkdir();(path/'history').write_text('own')
        data=await self.command(host);accepted=await delete(host,'project',self.pid,self.sid,data)
        self.assertEqual(await delete(host,'project',self.pid,self.sid,data),accepted)
        with patch('session_delete.remove',side_effect=OSError('Own simulated interruption')):
            await resume(host,'project',self.pid,self.sid,data['requestId'])
        with self.open() as store:
            self.assertEqual(original(store,self.sid,data['requestId'])['state'],'unknown')
            with self.assertRaises(ProjectFault):store.get(self.sid)
        # Coordinator restart only resumes this accepted original; no new request or inference.
        restarted=self.host();await recover(restarted)
        with self.open() as store:self.assertEqual(original(store,self.sid,data['requestId'])['state'],'deleted')
        with self.assertRaises(ProjectFault):await delete(host,'project',self.pid,self.sid,{**data,'confirmName':'foreign'})

    async def test_lifetime_gate_stale_revision_foreign_uuid_and_directory_identity(self):
        host=self.host();data=await self.command(host)
        with self.open() as store:
            store.row(self.sid)
            self.assertTrue((await preview(host,'project',self.pid,self.sid))['allowed'])
            with self.assertRaises(ProjectFault) as locked:await delete(host,'project',self.pid,self.sid,data)
            self.assertEqual(locked.exception.code,423)
            with store.db:store.db.execute('UPDATE sessions SET revision=2 WHERE id=?',(self.sid,))
        with self.assertRaises(ProjectFault):await delete(host,'project',self.pid,self.sid,data)
        with self.assertRaises(ProjectFault):await preview(host,'project',self.pid,str(uuid.uuid4()))
        data=await self.command(host);await delete(host,'project',self.pid,self.sid,data)
        with self.open() as store:
            (store.directory/self.sid).mkdir();(store.directory/self.sid/'new').write_text('preserve replacement')
        await resume(host,'project',self.pid,self.sid,data['requestId'])
        with self.open() as store:
            self.assertEqual(original(store,self.sid,data['requestId'])['state'],'unknown')
            self.assertEqual((store.directory/self.sid/'new').read_text(),'preserve replacement')

    async def test_transient_readers_allow_preview_confirmed_delete_and_original_cleanup_in_both_scopes(self):
        skill, skill_sid = self.add_skill(); host = self.host()
        for kind, owner, sid in [('project', self.pid, self.sid), ('skill', skill, skill_sid)]:
            async def after_reader(operation):
                # Model an already-running status/history read. A real flock is
                # held until the deletion request has had a chance to acquire it.
                with acquire(self.projects, kind, owner, sid):
                    pending = asyncio.create_task(operation())
                    await asyncio.sleep(0)
                return await pending

            view = await after_reader(lambda: preview(host, kind, owner, sid))
            self.assertTrue(view['allowed'], view)
            data = {'requestId': str(uuid.uuid4()), 'revision': view['revision'],
                    'scopeHash': view['scopeHash'], 'confirmName': view['name']}
            accepted = await after_reader(lambda: delete(host, kind, owner, sid, data))
            self.assertEqual(accepted['state'], 'deleting')
            await after_reader(lambda: resume(host, kind, owner, sid, data['requestId']))
            with closing(SessionStore(self.projects, self.r4os, owner, kind)) as store:
                self.assertEqual(original(store, sid, data['requestId'])['state'], 'deleted')

    async def test_rejected_uploads_and_confirmed_purges_allow_both_scopes_without_receipt_changes(self):
        from attachment_store import Attachments
        skill,skill_sid=self.add_skill();host=self.host()
        for kind,owner,sid in [('project',self.pid,self.sid),('skill',skill,skill_sid)]:
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                attachments=Attachments(store,sid)
                def upload(name):
                    raw=b'Own original upload bytes'
                    return attachments.upload({'requestId':str(uuid.uuid4()),'name':name,
                        'mediaType':'application/octet-stream','size':len(raw),
                        'sha256':hashlib.sha256(raw).hexdigest()},io.BytesIO(raw))
                rejected=upload('unsupported.bmp');self.assertEqual(rejected['state'],'rejected')
                purged=upload('unused.txt');attachments.remove(purged['attachment']['id'])
                self.assertEqual(attachments.row(purged['attachment']['id'])['state'],'purged')
                ready=upload('retained.txt');ready_path=Path(attachments.access(ready['attachment']['id'])['path'])
                original_bytes=ready_path.read_bytes()
                rows=[tuple(r) for r in store.db.execute('SELECT * FROM session_attachments ORDER BY id')]
            data=await self.command(host,kind,owner,sid)
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                self.assertEqual([tuple(r) for r in store.db.execute('SELECT * FROM session_attachments ORDER BY id')],rows)
                self.assertEqual(Attachments(store,sid).receipt(rejected['requestId']),rejected)
                self.assertEqual(ready_path.read_bytes(),original_bytes)
            await delete(host,kind,owner,sid,data)
            await resume(host,kind,owner,sid,data['requestId'])
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                self.assertEqual(original(store,sid,data['requestId'])['state'],'deleted')
                self.assertFalse(store.db.execute('SELECT 1 FROM session_attachments WHERE session_id=?',(sid,)).fetchone())
                self.assertFalse(ready_path.exists())

    async def test_abandoned_upload_receipts_block_migration_but_can_be_deleted_in_both_scopes(self):
        from attachment_store import Attachments
        skill,skill_sid=self.add_skill();host=self.host()
        for kind,owner,sid in [('project',self.pid,self.sid),('skill',skill,skill_sid)]:
            own_attachment,other_attachment,other_sid=(str(uuid.uuid4()) for _ in range(3))
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                row=store.row(sid);Attachments(store,sid).schema()
                with store.db:
                    store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')",(other_sid,owner,'Other session',row['settings'],row['engine']))
                    for ident,session,state in [(own_attachment,sid,'ready'),(other_attachment,other_sid,'pending')]:
                        store.db.execute("INSERT INTO session_attachments VALUES (?,?,?,'hash','{}',?,NULL,'{}','now')",(ident,session,str(uuid.uuid4()),state))
            for state in ('pending','unknown','removing','future-state'):
                with self.subTest(scope=kind,state=state):
                    with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store,store.db:
                        store.db.execute('UPDATE session_attachments SET state=? WHERE id=?',(state,own_attachment))
                    with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                        migration, _ = await inspect(host,store,sid,preserve_history=True)
                        self.assertIn('An attachment operation is active or unconfirmed.',migration['blockers'])
                    self.assertTrue((await preview(host,kind,owner,sid))['allowed'])
            data=await self.command(host,kind,owner,sid)
            await delete(host,kind,owner,sid,data)
            await resume(host,kind,owner,sid,data['requestId'])
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                self.assertEqual(original(store,sid,data['requestId'])['state'],'deleted')
                self.assertIsNone(store.db.execute('SELECT 1 FROM session_attachments WHERE id=?',(own_attachment,)).fetchone())
                self.assertEqual(store.db.execute('SELECT state FROM session_attachments WHERE id=?',(other_attachment,)).fetchone()[0],'pending')

    async def test_active_queue_and_goal_block_deletion_but_old_unknown_receipts_do_not(self):
        host=self.host()
        with self.open() as store:
            run,_=admit(store,self.sid,self.data,self.providers)
        self.assertFalse((await preview(host,'project',self.pid,self.sid))['allowed'])
        with self.open() as store:
            transition(store,run['id'],'completed')
            from message_store import Messages
            Messages(store).accept(self.sid,{'requestId':str(uuid.uuid4()),'revision':1,'mode':'queue','text':'Own queued work'},self.providers)
        self.assertFalse((await preview(host,'project',self.pid,self.sid))['allowed'])
        with self.open() as store:
            with store.db:store.db.execute("UPDATE session_messages SET state='removed' WHERE session_id=?",(self.sid,))
            from goal_store import Goals
            Goals(store).schema()
            with store.db:store.db.execute("INSERT INTO session_goals VALUES (?,1,NULL,NULL,'pending',NULL,NULL,NULL)",(self.sid,))
        self.assertFalse((await preview(host,'project',self.pid,self.sid))['allowed'])
        with self.open() as store:
            with store.db:
                store.db.execute("UPDATE session_goals SET phase='unknown' WHERE session_id=?",(self.sid,))
                store.db.execute("INSERT INTO tools VALUES (?,?,?,'hash','unknown','{}',NULL)",(run['id'],'own-call','studio_exec_command'))
            migration, _ = await inspect(host,store,self.sid,preserve_history=True)
            self.assertTrue(any('original tool effect' in reason for reason in migration['blockers']))
        data=await self.command(host);await delete(host,'project',self.pid,self.sid,data)
        await resume(host,'project',self.pid,self.sid,data['requestId'])
        with self.open() as store:
            self.assertEqual(original(store,self.sid,data['requestId'])['state'],'deleted')
            self.assertFalse(store.db.execute('SELECT 1 FROM runs WHERE id=?',(run['id'],)).fetchone())

    async def test_deletion_stops_only_its_analysis_service_and_discards_its_unknown_result(self):
        from skill_session_state import paths, registry
        host=self.host()
        own={'schema':1,'ownerType':'project','ownerId':self.pid,'sessionId':self.sid,
             'skillId':str(uuid.uuid4()),'serviceId':str(uuid.uuid4())}
        foreign={**own,'sessionId':str(uuid.uuid4()),'serviceId':str(uuid.uuid4())}
        for launch in (own,foreign):
            path=registry(self.projects,launch['serviceId']);path.mkdir(parents=True)
            (path/'Launch.json').write_text(encode(launch))
            calls=paths(self.projects,launch)[3]/'Transport/Calls';calls.mkdir(parents=True)
            (calls/'original.json').write_text(encode({'phase':'unknown'}))
        data=await self.command(host)
        with patch('skill_session_client.stop_unit',new_callable=AsyncMock) as stop:
            await delete(host,'project',self.pid,self.sid,data)
            await resume(host,'project',self.pid,self.sid,data['requestId'])
            stop.assert_awaited_once_with('r4os-studio-skill-mcp@'+own['serviceId']+'.service')
        self.assertFalse(registry(self.projects,own['serviceId']).exists())
        self.assertFalse(paths(self.projects,own)[3].exists())
        self.assertTrue(registry(self.projects,foreign['serviceId']).exists())
        self.assertTrue(paths(self.projects,foreign)[3].exists())

    async def test_external_remote_and_guest_effects_block_and_unrelated_session_remains_usable(self):
        host=self.host()
        import sqlite3
        path=self.projects/self.pid/'RemoteHosts/Jobs.sqlite';path.parent.mkdir()
        with closing(sqlite3.connect(path)) as db,db:db.execute('CREATE TABLE jobs(session_id TEXT,state TEXT)');db.execute('INSERT INTO jobs VALUES (?,?)',(self.sid,'unknown'))
        view=await preview(host,'project',self.pid,self.sid);self.assertFalse(view['allowed']);self.assertIn('remote',view['blockers'][0])
        with closing(sqlite3.connect(path)) as db,db:db.execute("UPDATE jobs SET state='completed'")
        await self.command(host)
        development=self.projects/self.pid/'Development/Development.sqlite';development.parent.mkdir()
        job_id=str(uuid.uuid4());proof_id=str(uuid.uuid4())
        job={'id':job_id,'projectId':self.pid,'sessionId':self.sid,'kind':'execution','state':'unknown','guestState':{'closeConfirmed':False}}
        with closing(sqlite3.connect(development)) as db,db:
            db.execute('CREATE TABLE jobs(id TEXT,busy INTEGER,payload TEXT)');db.execute('INSERT INTO jobs VALUES (?,0,?)',(job_id,encode(job)))
            db.execute('CREATE TABLE recoveries(id TEXT,job_id TEXT,receipt TEXT)')
        self.assertFalse((await preview(host,'project',self.pid,self.sid))['allowed'])
        proof={'id':proof_id,'schema':1,'source':'private-guest-close-receipt','guestEndConfirmed':True,'replayed':False}
        job['guestState']['closeConfirmed']=True;job['recovery']=proof
        with closing(sqlite3.connect(development)) as db,db:
            db.execute('UPDATE jobs SET payload=?',(encode(job),));db.execute('INSERT INTO recoveries VALUES (?,?,?)',(proof_id,job_id,encode(proof)))
        await self.command(host)
        with patch('session_delete.unit_states',new=AsyncMock(return_value=True)):
            self.assertFalse((await preview(host,'project',self.pid,self.sid))['allowed'])
