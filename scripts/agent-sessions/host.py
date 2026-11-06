#!/usr/bin/env python3
"""Unprivileged fixed-operation agent coordinator. Runs live in separate units."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from coordinator_work import ReadWork

from profile import write_json, directory
from session_store import SessionStore, identity, encode
from run_store import admit, get_run, transition, events
from protocol import release_protocol, supported_profiles, validate_release
from store import ProjectFault
from owner import binding, owners, skills_root
from run_limits import max_active_runs

UNIT = 'r4os-studio-agent@{}.service'


async def systemctl(*args):
    proc = await asyncio.create_subprocess_exec('/usr/bin/systemctl', '--no-ask-password', *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    output, _ = await asyncio.wait_for(proc.communicate(), 20)
    if proc.returncode: raise ProjectFault('The agent run service could not be controlled.', 503)
    return output.decode().strip()


class Host:
    def __init__(self, config):
        self.config = config
        self.max_active_runs = max_active_runs(config)
        self.root = directory(Path(config['projects']) / '.studio/agents')
        self.lock = asyncio.Lock(); self.active = {}; self.unbound = set(); self.connections = set(); self.goal_tasks = {}
        self.goal_readback_lock = asyncio.Lock()
        self.image_capability_lock=asyncio.Lock()
        self.inboxes=set();self.keepalives=set()
        self.message_tasks={}
        self.skill_delete_tasks={}
        self.session_delete_tasks={}
        self.attachment_decodes=0
        self.catalog_lock=asyncio.Lock();self.catalog_tasks={}
        self.source_tasks={}
        self.claude_probe_lock=asyncio.Lock()
        from claude_auth import ClaudeAuth
        self.claude_auth=ClaudeAuth(config['providers'])
        from chatgpt_plan import Login
        self.plan_login=Login(config['providers'])
        from claude_plan import ClaudePlan
        self.claude_plan=ClaudePlan(config['providers'])
        self.stats_cursor=0;self.stats_sessions={};self.stats_observations={}
        self.read_work=ReadWork(ProjectFault)

    def store(self, ident, kind='project'): return SessionStore(self.config['projects'], self.config['r4os'], ident, kind)

    async def active_unit(self, run_id):
        state = await systemctl('show', UNIT.format(identity(run_id)), '--property=ActiveState', '--value')
        return state in ('active', 'activating', 'deactivating', 'reloading')

    async def goal_worker_matches(self, meta, row):
        config=json.loads(row['config'])
        if config['engine'].get('kind')!='studio' and not any(config.get(key) for key in ('goalExecution','claudeGoalExecution','nativeGoalPreparation','claudeGoalPreparation','studioGoalPreparation')):return True
        try:
            pid=int(await systemctl('show',UNIT.format(row['id']),'--property=MainPID','--value'))
            if pid<=0 or (Path('/proc')/str(pid)).stat().st_uid!=self.config['uid']:return False
            worker=json.loads(row['worker'] or '{}')
            if not worker:return row['state']=='queued'
            birth=(Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()[19]
            return (worker.get('pid')==pid and worker.get('birth')==birth and worker.get('release')==meta['release']
                and (Path('/proc')/str(pid)).stat().st_uid==self.config['uid'])
        except (OSError,ValueError,KeyError,IndexError):return False

    async def reconcile_ended(self,store,meta):
        row=get_run(store,meta['runId']);config=json.loads(row['config'])
        if row['busy']:return False
        auxiliary=config['engine'].get('kind')!='studio'
        if auxiliary and not (store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_model_calls'").fetchone()
                and store.db.execute("SELECT 1 FROM studio_model_calls WHERE run_id=? AND json_extract(data,'$.vision.purpose')='vision'",(row['id'],)).fetchone()):return False
        if binding(meta)!=(store.owner_type,store.owner_id) or row['session_id']!=meta['sessionId']:return False
        from model_operations import confirm_end
        observed=dict(line.split('=',1) for line in (await systemctl('show',UNIT.format(row['id']),
            '--property=ActiveState','--property=MainPID','--property=InvocationID','--property=ControlGroup',
            '--property=ExecMainPID','--property=ExecMainCode','--property=ExecMainStatus','--property=Result')).splitlines() if '=' in line)
        if not confirm_end(store,meta,observed,auxiliary=auxiliary):return False
        from vision_analysis import release_ended
        release_ended(store,row['id'],self.config['providers'])
        if auxiliary:return True
        from api_provider_store import ApiProviders
        worker=json.loads(get_run(store,row['id'])['worker'])
        ApiProviders(self.config['providers']).release(row['id'],store.owner_type,store.owner_id,row['session_id'],
            row['request_id'],config,{key:worker[key] for key in ('release','pid','birth')})
        return True

    def metadata(self, path):
        if path.resolve(strict=True) != path.absolute(): raise ValueError('Invalid worker record.')
        value = json.loads(path.read_text())
        binding(value)
        for key in ('runId', 'sessionId', 'providerId'): identity(value[key])
        if path.parent.name != value['runId'] or value['schema'] != 1: raise ValueError('Invalid worker record.')
        for key in ('projects', 'r4os', 'providers'):
            if value[key] != self.config[key]: raise ValueError('Invalid worker storage binding.')
        validate_release(value)
        return value

    async def recover(self):
        self.claude_auth.store.recover()
        from api_catalog_host import recover as recover_catalogs
        await recover_catalogs(self)
        from session_delete import recover as recover_session_deletions
        await recover_session_deletions(self)
        # Never restart a queued/model/tool operation on coordinator or host boot.
        manifests = {}
        for path in self.root.glob('*/worker.json'):
            try:
                value = self.metadata(path); manifests[value['runId']] = value
            except Exception: continue  # Preserve corrupt records; active units below fail closed.
        from store import connect
        from contextlib import closing
        with closing(connect(Path(self.config['projects']))) as db:
            projects = [r['id'] for r in db.execute("SELECT id FROM projects WHERE state='ready'")]
        registered = [('project', ident) for ident in projects] + owners(self.config['projects'])
        for kind, project_id in registered:
            # Inspect registered session databases only; no discovery/creation in
            # foreign project folders or pre-session legacy workspaces.
            root = skills_root(self.config['projects']) if kind == 'skill' else Path(self.config['projects'])
            if not (root / project_id / 'Sessions/Sessions.sqlite').is_file(): continue
            try: store = self.store(project_id, kind)
            except Exception: continue
            try:
                for row in store.db.execute('SELECT * FROM runs WHERE busy=1').fetchall():
                    value = manifests.get(row['id'])
                    if (value and binding(value) == (kind, project_id) and value['sessionId'] == row['session_id']
                            and await self.active_unit(row['id']) and await self.goal_worker_matches(value,row)):
                        self.active[row['id']] = value
                    else:
                        transition(store, row['id'], 'unknown', 'The run ended without a confirmed result; tool effects were not repeated.')
                        from worker import reconcile_items
                        try:
                            from image_recovery import reconcile
                            reconcile(store,row['session_id'],row['id'],finalizing=True)
                        except Exception:pass
                        reconcile_items(store, row['id'])
                        from goal_store import Goals
                        Goals(store).lost_worker(row['id'])
                from message_store import Messages, exists
                if exists(store):
                    Messages(store).recover()
                    for saved in store.db.execute('SELECT session_id FROM session_inboxes'):
                        self.inboxes.add((kind, project_id, saved['session_id']))
                from goal_store import Goals
                live_plays={(json.loads(r['config']).get('goalExecution') or json.loads(r['config']).get('claudeGoalExecution') or {}).get('requestId')
                    for r in store.db.execute('SELECT * FROM runs WHERE busy=1') if r['id'] in self.active}
                from claude_live_store import live_plays as live_claude_plays
                for run_id in self.active:live_plays.update(live_claude_plays(store,run_id))
                if __import__('goal_store').exists(store):
                    for command in store.db.execute("SELECT * FROM goal_commands WHERE state='pending'"):
                        target=json.loads(command['payload']).get('_claudeTarget')
                        if target and target['runId'] in self.active:live_plays.add(command['request_id'])
                    for command in store.db.execute("SELECT * FROM goal_commands WHERE state='pending' AND stage!='accepted'"):
                        target=json.loads(command['payload']).get('target')
                        if target and target['runId'] in self.active: live_plays.add(command['request_id'])
                Goals(store).recover(live_plays)
                from goal_keepalive import exists as keepalive_exists
                if keepalive_exists(store):
                    self.keepalives.update((kind,project_id,r['session_id']) for r in store.db.execute('SELECT session_id FROM session_keepalive WHERE active=1'))
                # Repair stale pending cards from earlier compatible releases
                # using confirmed receipts, without replaying any tool operation.
                finished = set()
                for row in store.db.execute('SELECT i.run_id,i.payload FROM items i JOIN runs r ON r.id=i.run_id WHERE r.busy=0'):
                    if json.loads(row['payload']).get('status') in ('pending', 'running'): finished.add(row['run_id'])
                for run_id in finished:
                    from worker import reconcile_items
                    reconcile_items(store, run_id, get_run(store, run_id)['state'])
                for row in store.db.execute("SELECT * FROM runs WHERE busy=0 AND json_extract(worker,'$.runEndProtocol')=1 AND json_extract(worker,'$.processEnd.confirmed') IS NULL").fetchall():
                    value=manifests.get(row['id'])
                    if value:
                        try:await self.reconcile_ended(store,value)
                        except (OSError,ProjectFault):pass  # Missing end evidence keeps the original lease.
                # A prior pass may have committed parent end before a child
                # credential-release acknowledgement. Recover that original
                # binding even when the parent end is already confirmed.
                if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_model_calls'").fetchone():
                    pending_vision=store.db.execute("SELECT DISTINCT r.* FROM runs r JOIN studio_model_calls c ON c.run_id=r.id WHERE r.busy=0 AND json_extract(c.data,'$.vision.purpose')='vision' AND json_extract(c.data,'$.vision.leaseReleased') IS NOT 1").fetchall()
                    for row in pending_vision:
                        value=manifests.get(row['id'])
                        if value:
                            try:await self.reconcile_ended(store,value)
                            except (OSError,ProjectFault):pass
            finally: store.close()
        await self.check_unbound()

    async def check_unbound(self):
        raw = await systemctl('list-units', '--all', '--state=active,activating,deactivating,reloading', '--plain', '--no-legend', '--no-pager', 'r4os-studio-agent@*.service')
        units = set()
        for line in raw.splitlines():
            match = re.match(r'^r4os-studio-agent@([a-f0-9-]{36})\.service\s', line.strip())
            if match: units.add(identity(match[1]))
        self.unbound = units - set(self.active)

    async def refresh(self):
        for run_id, meta in list(self.active.items()):
            if await self.active_unit(run_id): continue
            kind, ident = binding(meta)
            try: store = self.store(ident, kind)
            except ProjectFault as error:
                if error.code != 404: raise
                self.active.pop(run_id, None); continue
            try:
                row = get_run(store, run_id)
                if row['busy']:
                    transition(store, run_id, 'unknown', 'The run service stopped without a confirmed result.')
                    from worker import reconcile_items
                    reconcile_items(store, run_id)
                    from goal_store import Goals
                    Goals(store).lost_worker(run_id)
                from message_store import observe_run
                with store.db: observe_run(store, row['session_id'], run_id, row['state'], row['turn_id'])
                await self.reconcile_ended(store,meta)
                self.active.pop(run_id, None)
            finally: store.close()
        await self.check_unbound()

    async def handle(self, request):
        op = request.get('operation')
        from host_reads import OPERATIONS, read
        if op in OPERATIONS:
            return await self.read_work.run(read, self.config, request)
        if op in ('web_service','set_web_service'):
            from studio_web import settings as web_settings
            expected={'operation'} if op=='web_service' else {'operation','input'}
            if set(request)!=expected:raise ProjectFault('Invalid web service request.',400)
            return web_settings(self.config['projects'],request.get('input'))
        if op == 'skill_source_start':
            if set(request) != {'operation', 'ownerId', 'requestId'}:
                raise ProjectFault('Invalid source operation.', 400)
            from skill_source_host import start as start_source
            return await start_source(self, request['ownerId'], request['requestId'])
        if op in ('decode_pending_attachment','preview_generated_image'):
            from attachment_decode import decode_pending,preview_generated
            # The coordinator has a shared 512 MiB budget. Never run two
            # independently bounded raster/PDF decoder processes together.
            if self.attachment_decodes >= 1:
                raise ProjectFault('Attachment validation is busy. Existing uploads were preserved.', 429)
            self.attachment_decodes += 1
            try: return await asyncio.to_thread(decode_pending if op=='decode_pending_attachment' else preview_generated, self, request)
            finally: self.attachment_decodes -= 1
        if op == 'fallback_save':
            from global_fallback import update
            return await self.read_work.run(update,self.config['projects'],self.config['providers'],request.get('input'))
        if op == 'project_activity':
            from project_activity import snapshot
            return await snapshot(self)
        if op == 'claude_plan':
            action=request.get('action');owner=request.get('ownerId');plan=self.claude_plan
            if action=='list':return await self.read_work.run(plan.listing,owner)
            if action=='start':return await asyncio.to_thread(plan.start,request.get('input'),owner)
            if action=='callback':return await asyncio.to_thread(plan.callback,request.get('requestId'),request.get('redirectUrl'),owner)
            if action=='cancel':return await asyncio.to_thread(plan.cancel,request.get('requestId'),owner)
            raise ProjectFault('Invalid Claude browser account operation.',400)
        if op == 'chatgpt_plan':
            action=request.get('action');plan=self.plan_login.plan;browser_owner=request.get('ownerId')
            self.plan_login.owner(browser_owner)
            if action=='list':return plan.listing(browser_owner)
            if action=='start':
                return await self.plan_login.start(request.get('input'),browser_owner)
            if action=='callback':return await self.plan_login.callback(request.get('requestId'),request.get('redirectUrl'),browser_owner)
            if action=='cancel':return await self.plan_login.cancel(request.get('requestId'),browser_owner)
            if action=='finish':return await self.plan_login.finish(request.get('requestId'),browser_owner)
            raise ProjectFault('Invalid ChatGPT account operation.',400)
        if op == 'api_provider':
            from api_provider_store import ApiProviders
            store=ApiProviders(self.config['providers']);action=request.get('action')
            if action=='native_connect':
                from native_openai import prepare
                return await asyncio.to_thread(prepare,self.config['providers'],request.get('id'),request.get('name'),request.get('binding'))
            if action=='native_retire':
                from native_openai import retire
                await retire(self,identity(request.get('id')),request.get('remove') is True)
                return {'closed':True}
            if action=='list':return await self.read_work.run(store.listing)
            if action=='get':return await self.read_work.run(store.get,request.get('id'))
            if action=='receipt':return await self.read_work.run(store.receipt,request.get('id'),request.get('requestId'))
            if action=='creation_receipt':return await self.read_work.run(store.creation_receipt,request.get('requestId'))
            if action in ('connection_limits','connection_limit_refresh','connection_limit_receipt'):
                from connection_limits import Limits
                limits=Limits(self.config['providers']);ident=identity(request.get('id'))
                if action=='connection_limits':return await self.read_work.run(limits.listing,ident)
                if action=='connection_limit_receipt':return await self.read_work.run(limits.receipt,ident,request.get('requestId'))
                return await asyncio.to_thread(limits.refresh,ident,request.get('input'))
            if action in ('zai_quota','zai_quota_receipt','zai_quota_refresh'):
                from zai_quota import Quota
                ident=identity(request.get('id'));quota=Quota(self.config['providers'])
                if action=='zai_quota':return await self.read_work.run(quota.listing,ident)
                if action=='zai_quota_receipt':return await self.read_work.run(quota.receipt,ident,request.get('requestId'))
                from zai_quota_host import start as check_quota
                return await check_quota(self,ident,request.get('input'))
            if action in ('models','model_save','catalog_receipt','catalog_refresh'):
                from api_catalog import Catalogs
                catalogs=Catalogs(self.config['providers']);ident=identity(request.get('id'))
                if action=='models':return await self.read_work.run(catalogs.listing,ident)
                if action=='model_save':return catalogs.save_model(ident,request.get('input'))
                if action=='catalog_receipt':return await self.read_work.run(catalogs.receipt,ident,request.get('requestId'))
                from api_catalog_host import start
                return await start(self,ident,request.get('input'))
            if action not in ('create','update','disconnect','delete'):raise ProjectFault('Invalid API provider operation.',400)
            ident=None if action=='create' else identity(request.get('id'))
            if action in ('disconnect','delete') and store.get(ident)['kind']=='chatgpt-plan':await self.plan_login.cancel_provider(ident)
            result=await asyncio.to_thread(store.mutate,action,ident,request.get('input'))
            if action in ('disconnect','delete') and result['state']=='pending':
                from api_catalog_host import recover as close_catalogs
                await close_catalogs(self,ident)
                await self.handle({'operation':'cancel_provider','providerId':ident})
                if result['provider']['kind'] in ('claude-plan','openrouter'):
                    from connection_limits import Limits
                    await asyncio.to_thread(Limits(self.config['providers']).finish_reads,ident)
                if result['provider']['kind']=='chatgpt-plan':
                    revocation=await asyncio.to_thread(self.plan_login.plan.revoke,ident)
                elif result['provider']['kind']=='claude-plan':
                    await asyncio.to_thread(self.claude_plan.forget,ident)
                    revocation={'localLogout':'confirmed','remoteRevocation':'unconfirmed'}
                else:revocation=None
                result=await asyncio.to_thread(store.mutate,action,ident,request.get('input'),True)
                if revocation:result['planLogout']=revocation
            return result
        if op == 'capabilities': return {'visionAnalysis':1, 'visionFallbackSettings':1, 'systemTools':1, 'goalClockCycles':1, 'goalKeepalive':1, 'deferredModelChoice':1, 'studioGoals':1, 'enabled': not bool(self.unbound), 'protocol': 1, 'sessionDeletion':1, 'attachmentValidation':1, 'attachmentFiles':1, 'projectActivity':1, 'apiProviders':1, 'apiModelCatalog':1, 'apiOpenRouter':1, 'apiReasoningHistory':1, 'apiLocal':1, 'apiUsageOrigins':1, 'apiNativeGoals':1, 'claudeProviders':1, 'claudeMetadataControl':1, 'claudeAuthentication':1, 'claudeSubscriptionLimits':1, 'claudeGoals':1, 'claudeGoalExecution':1, 'claudeLiveGoals':1, 'apiResponses':1, 'apiChat':1, 'sessionMessages': 1, 'messageQueue': 1, 'claudeBoundMessages':1, 'messageSteering': 1, 'runReceipts': 1, 'statistics':1, 'skillDeletion':1, 'skillSources':1, 'skillMcp':1, 'environmentNotes':1, 'environmentNotesSettings':1, 'liveGoalPreparation':1, 'liveGoalControl':1, 'nativeGoals': 1, 'nativeGoalExecution': 2, 'nativeGoalReadback': 1, 'nativeImageInputs': 1, 'documentInputs': 1, 'imageGenerationSettings':1, 'projectDeletionLocks': 1, 'projectPinLocks': 1, 'projectInstructions': 1, 'vmStartTools': 1, 'skillSessions': 1, 'skillAuthorTools': 1, 'globalSkills': 1, 'skillScripts': 1, 'nativeWebSearch': 1, 'roadmapSettings': 1, 'roadmapTools': 1, 'remoteHostTools': 1, 'maxActiveRuns': self.max_active_runs, 'version': json.loads((Path(__file__).resolve().parents[2] / 'shared/version.json').read_text())['version']}
        if op == 'claude_provider':
            from claude_provider_store import ClaudeProviders
            store=ClaudeProviders(self.config['providers']);action=request.get('action')
            if action=='list':return await self.read_work.run(store.listing)
            if action=='get':return await self.read_work.run(store.get,request.get('id'))
            if action=='creation_receipt':return await asyncio.to_thread(store.receipt,request.get('requestId'))
            if action=='create':return await asyncio.to_thread(store.create,request.get('input'))
            if action in ('auth_start','auth_remove'):
                ident=identity(request.get('id'))
                data=request.get('input')
                if action=='auth_remove':
                    if not isinstance(data,dict) or set(data)!={'requestId','revision','confirmName'}:raise ProjectFault('Invalid Claude removal request.',400)
                    data={**data,'action':'remove'}
                elif isinstance(data,dict) and data.get('action')=='remove':raise ProjectFault('Use the confirmed Claude removal request.',400)
                async with self.lock:
                    await self.refresh()
                    if self.claude_probe_lock.locked():raise ProjectFault('A native Claude metadata probe is still active.',429)
                    if self.unbound or any(meta['providerId']==ident for meta in self.active.values()):
                        raise ProjectFault('Reconcile or finish original bound workers before changing Claude authentication. No worker was stopped.',409)
                    return await self.claude_auth.start(ident,data,request.get('owner'))
            if action=='auth_receipt':return self.claude_auth.view(identity(request.get('id')),identity(request.get('requestId')),request.get('owner'))
            if action=='limits':return await self.read_work.run(self.claude_auth.store.latest_limits,identity(request.get('id')))
            if action=='catalog':return await self.read_work.run(self.claude_auth.store.latest_catalog,identity(request.get('id')))
            if action=='auth_code':return await self.claude_auth.submit(identity(request.get('id')),identity(request.get('requestId')),request.get('owner'),request.get('code'))
            if action=='auth_cancel':return await self.claude_auth.cancel(identity(request.get('id')),identity(request.get('requestId')),request.get('owner'))
            if action=='runtime':
                from claude_runtime import installed
                runtime=await asyncio.to_thread(installed,self.config['providers'])
                return {key:runtime[key] for key in ('id','version','sdkVersion','sha256','sdkArchiveSha256','qualified')}
            if action=='probe':
                if self.claude_auth.busy:raise ProjectFault('A native Claude authentication operation is still active.',429)
                if self.claude_probe_lock.locked():raise ProjectFault('A Claude metadata probe is already active.',429)
                from claude_probe import probe
                async with self.claude_probe_lock:
                    return await probe(self.config['providers'],self.root,request.get('requestId'))
            raise ProjectFault('Unsupported Claude provider operation.',400)
        if op in ('session_zai_limits','session_zai_limit_refresh','session_zai_limit_receipt','session_connection_limits','session_connection_limit_refresh','session_connection_limit_receipt'):
            if op.startswith('session_connection_'):
                from connection_session_limits import dispatch
            else:
                from zai_session_limits import dispatch
            kind,ident=binding(request);store=self.store(ident,kind)
            try:return await dispatch(self,store,request['sessionId'],op,request.get('input'),request.get('requestId'))
            finally:store.close()
        if op=='session_claude_limits':
            kind,ident=binding(request);store=self.store(ident,kind)
            try:
                session=store.get(identity(request['sessionId']))
                if session['engine'].get('kind')!='claude-code':return {'limits':None,'observation':None}
                from claude_history import ClaudeHistory
                from claude_provider_store import account_identity
                original=ClaudeHistory(store,session['id']).get()
                provider=self.claude_auth.store.get(session['providerId'])
                if account_identity(provider['account'])!=original['accountIdentity']:
                    return {'limits':None,'observation':None}
                latest=store.db.execute("SELECT payload FROM events WHERE session_id=? AND kind='claudeQuota' ORDER BY seq DESC LIMIT 1",(session['id'],)).fetchone()
                observed=json.loads(latest[0]) if latest else None
                if observed and observed.get('accountIdentity')!=original['accountIdentity']:observed=None
                from claude_quota_store import QuotaStore
                quota=QuotaStore(self.config['providers']).read(provider['id'])
                limits=self.claude_auth.store.latest_limits(session['providerId'])
                sample=quota.get('sample') if quota else None
                if (sample and sample.get('providerId')==provider['id'] and sample.get('providerRevision')==provider['revision']
                    and sample.get('accountIdentity')==original['accountIdentity']
                    and (not limits or sample['receivedAt']>limits['receivedAt'])):limits=sample
                return {'limits':limits,'observation':observed,'hold':quota['hold'] if quota else None,'providerRevision':provider['revision']}
            finally:store.close()
        if op in ('session_migration_status','session_migration_preview','session_migrate','session_migration_rollback'):
            from session_migration import dispatch
            async with self.lock: return await dispatch(self, request)
        if op in ('session_delete_preview','session_delete'):
            import session_delete
            kind,ident=binding(request);sid=identity(request['sessionId'])
            if op=='session_delete_preview': return await session_delete.preview(self,kind,ident,sid)
            rid=identity(request['input']['requestId'])
            if len(self.session_delete_tasks)>=2 and rid not in self.session_delete_tasks:
                raise ProjectFault('Session cleanup is busy. Read the original request before retrying.',429)
            result=await session_delete.delete(self,kind,ident,sid,request['input'])
            if result['state']!='deleted' and rid not in self.session_delete_tasks:
                task=asyncio.create_task(session_delete.resume(self,kind,ident,sid,rid));self.session_delete_tasks[rid]=task
                task.add_done_callback(lambda _,rid=rid:self.session_delete_tasks.pop(rid,None))
            return result
        if op in ('skill_delete_preview','skill_delete','skill_delete_receipt'):
            import skill_delete
            ident=identity(request['ownerId'])
            try:
                if op=='skill_delete_receipt':
                    from contextlib import closing
                    with closing(skill_delete.packages.connect(skills_root(self.config['projects']))) as db:return skill_delete.original(db,request['requestId'],ident)
                if op=='skill_delete_preview':
                    with skill_delete.lifecycle.lock(skills_root(self.config['projects']),fault=ProjectFault):return (await skill_delete.preview(self,ident))[0]
                rid=identity(request['input']['requestId'])
                if len(self.skill_delete_tasks)>=2 and rid not in self.skill_delete_tasks:raise ProjectFault('Skill cleanup is busy. Read the original request before retrying.',429)
                result=await skill_delete.delete(self,ident,request['input'])
                if result['state']!='deleted' and rid not in self.skill_delete_tasks:
                    task=asyncio.create_task(skill_delete.resume(self,rid));self.skill_delete_tasks[rid]=task
                    task.add_done_callback(lambda _,rid=rid:self.skill_delete_tasks.pop(rid,None))
                return result
            except skill_delete.packages.SkillFault as error:raise ProjectFault(str(error),error.code) from None
        if op == 'cancel_provider':
            provider_id = identity(request['providerId'])
            async with self.lock:
                await self.refresh()
                if self.unbound: raise ProjectFault('Reconcile unbound agent workers before disconnecting a provider.', 503)
                for run_id, meta in list(self.active.items()):
                    if meta['providerId'] == provider_id:
                        kind, ident = binding(meta)
                        await self.stop(ident, meta['sessionId'], run_id, kind)
            return {'stopped': True}
        kind, project_id = binding(request)
        session_id = identity(request['sessionId'])
        if op=='choose_model':
            from model_choice import Choices
            async with self.lock:
                await self.refresh()
                store=self.store(project_id,kind)
                try:return Choices(store).accept(session_id,request['input'],self.config['providers'],bool(self.unbound))
                finally:store.close()
        if op == 'delete_environment_notes':
            from environment_notes import Notes
            store=self.store(project_id,kind)
            try:
                notes=Notes(store)
                return notes.delete(session_id,request['input'],request.get('noteId'))
            finally:store.close()
        if op in ('submit_message', 'message_control'):
            from message_store import Messages
            capability = None
            if op == 'submit_message' and request.get('input',{}).get('mode') != 'steer':
                preliminary = self.store(project_id, kind)
                try:
                    from model_choice import capture as model_capture
                    selected,_ = model_capture(preliminary,session_id,preliminary.get(session_id))
                    from message_store import exists
                    previous = exists(preliminary) and preliminary.db.execute('SELECT 1 FROM session_messages WHERE request_id=?', (request['input'].get('requestId'),)).fetchone()
                    latest = preliminary.db.execute('SELECT config FROM runs WHERE session_id=? ORDER BY created_at DESC LIMIT 1', (session_id,)).fetchone()
                    if latest:
                        from image_generation import freeze
                        saved = json.loads(latest['config']).get('imageGenerationCapability')
                        if saved and all(saved.get(k) == selected.get(k) for k in ('providerId','model','engine')): capability = freeze(selected, saved)
                    if not previous and capability is None and selected.get('imageGenerationEnabled', True):
                        from image_generation import inspect
                        if self.image_capability_lock.locked(): raise ProjectFault('Image capability is busy. Your message was preserved.', 429)
                        async with self.image_capability_lock: capability = await inspect(preliminary, session_id, self.config['providers'],{'model':selected['model']})
                finally: preliminary.close()
            async with self.lock:
                if op == 'message_control': await self.refresh()
                store = self.store(project_id, kind)
                try:
                    store.row(session_id)
                    messages = Messages(store)
                    self.inboxes.add((kind, project_id, session_id))
                    if op == 'message_control': return messages.control(session_id, request['input'],self.config['providers'])
                    flags = {'nativeWebSearch':1,'skillSelection':1,'skillScripts':1,'skillMcp':1,'nativeImageInputs':1,'documentInputs':1,'imageGenerationSettings':1,'liveGoalPreparation':1,'environmentNotesSettings':1,
                             **({'projectInstructions':1,'roadmapSettings':1,'remoteHostTools':1} if kind=='project' else {})}
                    if store.db.execute('SELECT 1 FROM session_messages WHERE request_id=?', (request['input'].get('requestId'),)).fetchone():
                        # An original receipt outlives its active worker/turn.
                        # Compare the immutable input before checking fresh targets.
                        return messages.accept(session_id, request['input'], self.config['providers'], flags, capability)[0]
                    direct_target=request['input'].get('target') if request['input'].get('mode')=='steer' else request['input'].get('afterRun')
                    if direct_target:
                        meta = self.active.get(direct_target.get('runId'))
                        if not meta or binding(meta)!=(kind,project_id) or meta['sessionId']!=session_id:
                            raise ProjectFault('The response target has no confirmed original worker binding.',409)
                        validate_release(meta)
                        original = get_run(store, direct_target['runId'])
                        if json.loads(original['worker'] or '{}').get('release') != meta['release']:
                            raise ProjectFault('The response target no longer has its original worker release.',403)
                    message, fresh = messages.accept(session_id, request['input'], self.config['providers'], flags, capability)
                    if fresh and message['mode']=='steer':
                        key = (kind,project_id,session_id,message['requestId'])
                        task = asyncio.create_task(self.deliver_message(*key));self.message_tasks[key]=task
                        task.add_done_callback(lambda _, key=key: self.message_tasks.pop(key,None))
                    return message
                finally: store.close()
        if op=='image_generation_capability':
            from image_generation import inspect
            if self.image_capability_lock.locked():raise ProjectFault('Another image capability read is in progress. Try again shortly.',429)
            async with self.image_capability_lock:
                store=self.store(project_id,kind)
                try:return await inspect(store,session_id,self.config['providers'],request.get('selection'))
                finally:store.close()
        if op=='goal_readback':
            current=self.store(project_id,kind)
            try:
                from goal_keepalive import row as keepalive_row
                if keepalive_row(current,session_id):
                    from goal_store import Goals
                    return {'goal':Goals(current).snapshot(session_id),'nativeRead':False,'superseded':False}
            finally:current.close()
            from goal_readback import readback
            if self.goal_readback_lock.locked():raise ProjectFault('Another native Goal readback is in progress.',429)
            async with self.goal_readback_lock:
                store=self.store(project_id,kind)
                try:return await asyncio.wait_for(readback(store,session_id),15)
                finally:store.close()
        if op == 'goal_command':
            from goal_store import Goals
            async with self.lock:
                store = self.store(project_id, kind)
                try:
                    goals = Goals(store)
                    if self.unbound and request['input'].get('action') not in ('pause','stop'):
                        raise ProjectFault('Reconcile the original unbound workers before starting a Goal.',503)
                    result, fresh = goals.accept(session_id, request['input'])
                    if result['snapshot'].get('keepalive') is not None:
                        key=(kind,project_id,session_id)
                        from goal_keepalive import row as keepalive_row
                        current=keepalive_row(store,session_id)
                        if current and current['active']:self.keepalives.add(key)
                        else:self.keepalives.discard(key)
                        return result
                    if request['input'].get('action') in ('pause','stop'):
                        from message_store import Messages
                        Messages(store).hold(session_id, 'The user paused or stopped this session. Continue explicitly.')
                    if fresh:
                        key=(kind,project_id,session_id,result['requestId'])
                        task=asyncio.create_task(self.goal_command(*key)); self.goal_tasks[key]=task
                        task.add_done_callback(lambda _, key=key: self.goal_tasks.pop(key,None))
                    return result
                finally: store.close()
        if op == 'stop_run':
            async with self.lock: return await self.stop(project_id, session_id, identity(request['runId']), kind)
        if op == 'start_run':
            image_capability=None
            if request.get('input',{}).get('imageGenerationSettings')==1:
                preliminary=self.store(project_id,kind)
                try:
                    previous=preliminary.db.execute('SELECT 1 FROM runs WHERE request_id=?',(request['input'].get('requestId'),)).fetchone()
                    from model_choice import capture as model_capture
                    selected,_=model_capture(preliminary,session_id,preliminary.get(session_id))
                    if not previous and selected.get('imageGenerationEnabled',True):
                        from image_generation import inspect
                        if self.image_capability_lock.locked():raise ProjectFault('An image capability read is in progress. No run was started; try again shortly.',429)
                        async with self.image_capability_lock:image_capability=await inspect(preliminary,session_id,self.config['providers'],{'model':selected['model']})
                finally:preliminary.close()
            async with self.lock:
                await self.refresh()
                if self.unbound: raise ProjectFault('An agent worker has no confirmed binding. Restore host support before starting another run.', 503)
                store = self.store(project_id, kind)
                try:
                    if store.get(session_id)['engine'].get('api'):
                        target=Path(self.config.get('workerReleaseRoot','/opt/r4os-studio/current')).resolve(strict=True)
                        adapters=['api_runtime.py','api-transport.mjs','api-model-launcher.py','api_chat.mjs','api_openrouter.mjs','api_local.mjs','api_server.py','api_usage.py','api_usage.mjs']
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not all((target/'scripts/agent-sessions'/name).is_file() for name in adapters):
                            raise ProjectFault('This worker release cannot preserve the API transport binding. No model was started.',503)
                    # Duplicate requests are admitted idempotently even at capacity.
                    previous = store.db.execute('SELECT id FROM runs WHERE request_id=?', (request['input'].get('requestId'),)).fetchone()
                    if not previous and request['input'].get('documentInputs')==1:
                        target=Path(self.config.get('workerReleaseRoot','/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target/'scripts/agent-sessions/document_inputs.py').is_file():
                            raise ProjectFault('This worker release cannot provide the saved document input contract.',503)
                    from image_inputs import history as image_history
                    if not previous and (request['input'].get('nativeImageInputs')==1 or image_history(store,session_id)):
                        target=Path(self.config.get('workerReleaseRoot','/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target/'scripts/agent-sessions/image_inputs.py').is_file():
                            raise ProjectFault('This worker release cannot preserve native image inputs. The conversation and attachments were preserved.',503)
                    if not previous and request['input'].get('mode') == 'goal':
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        required=('claude_goal.py','claude_goal_worker.py') if store.get(session_id)['engine'].get('kind')=='claude-code' else ('goal_worker.py',)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not all((target/'scripts/agent-sessions'/name).is_file() for name in required):
                            raise ProjectFault('This worker release cannot preserve the original Goal engine contract.',503)
                    if not previous and request['input'].get('roadmapSettings') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if kind != 'project' or not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/roadmap_access.py').is_file():
                            raise ProjectFault('This worker release cannot provide the saved Roadmap setting.', 503)
                    if not previous and request['input'].get('nativeWebSearch') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/web_search.py').is_file():
                            raise ProjectFault('This worker release cannot provide the saved Web search setting.', 503)
                    if not previous and request['input'].get('skillSelection') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/skill_application.py').is_file():
                            raise ProjectFault('This worker release cannot apply the saved session skill choices.', 503)
                        if request['input'].get('skillScripts') == 1 and not (target / 'scripts/agent-sessions/skill_scripts.py').is_file():
                            raise ProjectFault('This worker release cannot provide frozen skill script resources.', 503)
                    if not previous and request['input'].get('skillMcp') == 1:
                        target = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target / 'scripts/agent-sessions/skill_mcp_tools.py').is_file():
                            raise ProjectFault('This immutable worker release cannot provide managed skill tools.',503)
                    if not previous and len(self.active) >= self.max_active_runs:
                        raise ProjectFault(f'The host is already running its maximum number of agent runs ({self.max_active_runs}). No run was started. Retry the same request when a slot is available.', 429)
                    if not previous:
                        from model_choice import prepare as prepare_model_choice
                        await prepare_model_choice(self,store,session_id,request['input'])
                    run, fresh = admit(store, session_id, request['input'], self.config['providers'],image_capability)
                    if not fresh: return run
                    return await self.launch_admitted(store, run, kind, project_id, session_id)
                finally: store.close()
        raise ProjectFault('Unsupported agent coordinator operation.', 400)

    async def launch_admitted(self, store, run, kind, project_id, session_id):
        try:
            release = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
            from studio_engine import release_for
            release=release_for(json.loads(get_run(store,run['id'])['config'])['engine'],release)
            if not release.is_relative_to('/opt/r4os-studio/releases'): raise ProjectFault('Invalid agent worker release.', 503)
            release_protocol(release)
            if not (release / 'scripts/agent-sessions/instructions.py').is_file():
                raise ProjectFault('This worker release cannot apply project instructions.', 503)
            info = json.loads((release / 'release.json').read_text())
            meta = {'schema': 1, 'runId': run['id'], 'ownerType': kind, 'ownerId': project_id, 'sessionId': session_id,
                    'providerId': store.get(session_id)['providerId'], 'projects': self.config['projects'],
                    'r4os': self.config['r4os'], 'providers': self.config['providers'],
                    'releaseRoot': str(release), 'release': info['id'], 'version': info['version']}
            if kind == 'project': meta['projectId'] = project_id
            parent = directory(self.root / run['id']); write_json(parent / 'worker.json', meta)
            self.active[run['id']] = meta
            await systemctl('start', '--no-block', UNIT.format(run['id']))
        except Exception:
            # A lost systemctl response may still have started a unit.
            # Keep its durable admission while it is alive or unknown.
            try: alive = await self.active_unit(run['id'])
            except Exception: alive = True
            if not alive:
                self.active.pop(run['id'], None)
                transition(store, run['id'], 'failed', 'The agent run service could not start.')
            raise
        return run

    async def deliver_message(self, kind, ident, sid, request_id):
        from message_store import Messages
        from message_worker import live_message
        store = self.store(ident,kind)
        try:
            await live_message(store,sid,request_id)
        except BaseException as error:
            state = 'rejected' if isinstance(error,(FileNotFoundError,ConnectionRefusedError)) or isinstance(error,ProjectFault) and error.code in (403,404) else 'unknown'
            messages=Messages(store);row=messages.row(sid,request_id)
            registered=json.loads(row['frozen']).get('config',{}).get('engine',{}).get('kind')=='studio' and row['state'] in ('dispatching','accepted')
            if not registered:messages.finish(sid,request_id,state,'The original direct worker receipt could not be confirmed. No message was submitted again.')
            if isinstance(error,asyncio.CancelledError): raise
        finally: store.close()

    async def dispatch_queues(self):
        from message_store import Messages
        if self.unbound or len(self.active) >= self.max_active_runs: return
        for kind, ident, sid in tuple(self.inboxes):
            if len(self.active) >= self.max_active_runs: return
            store = None
            try:
                store = self.store(ident, kind)
                messages = Messages(store)
                row = messages.first(sid)
                if row is None: continue
                if store.db.execute('SELECT 1 FROM runs WHERE busy=1').fetchone(): continue
                if any(binding(meta) == (kind, ident) for meta in self.active.values()): continue
                frozen = json.loads(row['frozen'])
                if 'config' not in frozen or 'runInput' not in frozen:
                    messages.hold(sid, 'This legacy queued input has no frozen run selection. Remove and submit it explicitly.'); continue
                from claude_messages import validate_queue
                validate_queue(store,sid,frozen)
                from goal_store import Goals, pending
                goal = Goals(store).snapshot(sid)
                if pending(store) or goal['phase'] not in ('idle',): continue
                if not goal.get('keepalive') and goal['goal'] and goal['goal']['status'] == 'active':
                    messages.hold(sid, 'Pause the original Goal before continuing this queue.'); continue
                if not goal.get('keepalive') and goal['goal'] and goal['goal'].get('source')=='studio' and goal['goal']['status'] in ('budgetLimited','usageLimited','blocked'):
                    last=store.db.execute('SELECT id FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
                    if last and goal.get('runId')==last['id'] and not messages.resumed_after(sid,last['id']):
                        messages.hold(sid,'Review the original Goal limit or blockade and continue this queue explicitly.');continue
                config = frozen['config']
                from model_choice import prepare as prepare_model_choice
                await prepare_model_choice(self,store,sid,frozen['runInput'],config)
                from studio_engine import release_for
                release_for(config['engine'],Path(self.config.get('workerReleaseRoot','/opt/r4os-studio/current')).resolve(strict=True))
                run, fresh = admit(store, sid, frozen['runInput'], self.config['providers'], config.get('imageGenerationCapability'), config)
                if not fresh:
                    messages.hold(sid, 'The original queued run already exists. Inspect its receipt; it was not started again.'); continue
                await self.launch_admitted(store, run, kind, ident, sid)
            except Exception as error:
                if isinstance(error,ProjectFault) and error.code==423:continue
                if store:
                    try: Messages(store).hold(sid, str(error) if isinstance(error, ProjectFault) else 'Queue dispatch could not be confirmed. Read the original message receipt.')
                    except Exception: pass
            finally:
                if store: store.close()

    async def goal_command(self, kind, project_id, sid, rid):
        from goal_store import Goals
        from goal_control import idle_control, live_control
        store=self.store(project_id,kind); goals=Goals(store)
        try:
            data=json.loads(goals.command(sid,rid)['payload'])
            if store.get(sid)['engine'].get('kind')=='claude-code':
                await self.claude_goal_command(store,sid,rid,kind,project_id);return
            if data.get('target'):
                await live_control(store,sid,rid)
                if data['action']=='stop': await self.stop(project_id,sid,data['target']['runId'],kind)
                return
            if data['action']=='play':
                session=store.get(sid)
                goals.stage(sid,rid,'admitting_worker')
                try:
                    run=await self.handle({'operation':'start_run','ownerType':kind,'ownerId':project_id,'sessionId':sid,
                        'input':{'mode':'goal','goalRequestId':rid,'requestId':rid,'revision':session['revision'],
                            'nativeWebSearch':1,'skillSelection':1,'skillScripts':1,'skillMcp':1,'nativeImageInputs':1,'documentInputs':1,'imageGenerationSettings':1,'liveGoalPreparation':1,'environmentNotesSettings':1,
                            **({'projectInstructions':1,'roadmapSettings':1,'remoteHostTools':1} if kind=='project' else {})}})
                except Exception:
                    original=store.db.execute('SELECT * FROM runs WHERE request_id=? AND session_id=?',(rid,sid)).fetchone()
                    if not original or not original['busy']:
                        goals.finish(sid,rid,'failed' if not original or original['state']=='failed' else 'unknown',
                            'The original Goal run was not confirmed. No second run was submitted.')
                        return
                    run=store.run_present(original)
                goals.stage(sid,rid,'worker_queued')
                with store.db: store.db.execute('UPDATE session_goals SET run_id=? WHERE session_id=?',(run['id'],sid))
                # Worker owns activation and final Play receipt. No second RPC.
                return
            busy=store.db.execute('SELECT * FROM runs WHERE busy=1').fetchone()
            if busy:
                if busy['session_id']!=sid: raise ProjectFault('Another session is using this workspace.',409)
                if not json.loads(busy['config']).get('goalExecution'):
                    if data['action']!='stop': raise ProjectFault('Wait for the ordinary run to finish before changing this Goal.',409)
                    await self.stop(project_id,sid,busy['id'],kind)
                else:
                    for attempt in range(30):
                        try:
                            await live_control(store,sid,rid)
                            if data['action'] in ('save','stop'):
                                await self.stop(project_id,sid,busy['id'],kind)
                                if data['action']=='save': await idle_control(store,sid,rid,self.config['providers'])
                                else: goals.finish(sid,rid)
                            return
                        except (FileNotFoundError,ConnectionRefusedError):
                            if attempt==29: raise
                            await asyncio.sleep(.1)
            await idle_control(store,sid,rid,self.config['providers'])
        except BaseException as error:
            row=goals.command(sid,rid)
            goals.finish(sid,rid,'failed' if row['stage']=='accepted' else 'unknown',
                str(error) if isinstance(error,ProjectFault) else 'The original Goal command could not be confirmed. Read its result before another action.')
            if isinstance(error,asyncio.CancelledError): raise
        finally: store.close()

    async def claude_goal_command(self,store,sid,rid,kind,owner):
        from goal_store import Goals
        from claude_goal_store import idle
        from goal_control import live_control
        goals=Goals(store);data=json.loads(goals.command(sid,rid)['payload'])
        if data.get('_claudeLiveTarget'):
            await live_control(store,sid,rid);return
        if data['action']=='play':
            session=store.get(sid);goals.stage(sid,rid,'admitting_worker')
            try:
                run=await self.handle({'operation':'start_run','ownerType':kind,'ownerId':owner,'sessionId':sid,
                    'input':{'mode':'goal','goalRequestId':rid,'requestId':rid,'revision':session['revision'],
                        'skillSelection':1,'skillScripts':1,'skillMcp':1,'environmentNotesSettings':1,
                        **({'projectInstructions':1,'roadmapSettings':1,'remoteHostTools':1} if kind=='project' else {})}})
            except Exception as error:
                original=store.db.execute('SELECT * FROM runs WHERE request_id=? AND session_id=?',(rid,sid)).fetchone()
                if not original or not original['busy']:
                    goals.finish(sid,rid,'failed' if not original or original['state']=='failed' else 'unknown',
                        str(error) if isinstance(error,ProjectFault) else 'The original bounded Claude Goal run was not confirmed. No second run was submitted.')
                    return
                run=store.run_present(original)
            goals.stage(sid,rid,'worker_queued')
            with store.db:store.db.execute('UPDATE session_goals SET run_id=? WHERE session_id=?',(run['id'],sid))
            return  # Actual native input acknowledgement confirms this Play.
        if data.get('_claudeTarget'):
            await live_control(store,sid,rid)
            if data['action']=='stop':await self.stop(owner,sid,data['_claudeTarget']['runId'],kind)
        else:idle(goals,sid,rid)

    async def stop(self, project_id, session_id, run_id, kind='project'):
        store = self.store(project_id, kind)
        try:
            store.row(session_id)
            row = get_run(store, run_id)
            if row['session_id'] != session_id: raise ProjectFault('Run not found.', 404)
            from message_store import Messages
            Messages(store).hold(session_id, 'The user stopped this session. Continue the queue explicitly.')
            if row['busy'] or await self.active_unit(run_id):
                transition(store, run_id, 'stopping')
                await systemctl('stop', UNIT.format(run_id))
                if await self.active_unit(run_id):raise ProjectFault('The original run service end is unconfirmed. Its resources remain protected.',503)
                row = get_run(store, run_id)
                if row['busy']: transition(store, run_id, 'interrupted', 'Run stopped.')
            self.active.pop(run_id, None)
            self.unbound.discard(run_id)
            path=self.root/run_id/'worker.json'
            if path.exists():await self.reconcile_ended(store,self.metadata(path))
            if json.loads(row['config']).get('claudeGoalExecution') or json.loads(row['config']).get('claudeGoalPreparation'):
                from claude_goal import lost as lost_claude
                from goal_clock import lost as lost_claude_clock
                lost_claude(store,run_id);lost_claude_clock(store,run_id)
                from goal_store import Goals
                Goals(store).lost_worker(run_id)
            if json.loads(row['config']).get('goalExecution'):
                from goal_store import Goals
                goals=Goals(store);goals.lost_worker(run_id)
                snapshot=goals.snapshot(session_id)
                if snapshot['goal'] and snapshot['goal']['status']=='paused':
                    with store.db:
                        store.db.execute("UPDATE session_goals SET last_intent='stop',phase=CASE WHEN phase='pending' THEN phase ELSE 'idle' END,revision=revision+1 WHERE session_id=?",(session_id,))
                        goals.publish(session_id)
            return store.run_present(get_run(store, run_id))
        finally: store.close()

    async def reconcile_statistics(self):
        if getattr(self,'stats_work_running',False): return
        self.stats_work_running=True
        cursor=self.stats_cursor
        from host_reads import reconcile_statistics
        try:
            active_owners=set()
            for meta in self.active.values():
                try:active_owners.add(binding(meta))
                except ProjectFault:pass
            result=await self.read_work.run(reconcile_statistics,self.config,cursor,dict(self.stats_sessions),
                dict(getattr(self,'stats_observations',{})),active_owners,bool(self.unbound))
            if cursor!=self.stats_cursor: return  # Discard an obsolete cursor result.
            self.stats_cursor=result[0]
            if result[1] is not None and result[2] is not None:self.stats_sessions[result[1]]=result[2]
            if result[3] is not None:
                key,value=result[3]
                if not hasattr(self,'stats_observations'):self.stats_observations={}
                self.stats_observations.pop(key,None)
                if value is not None:self.stats_observations[key]=value
                from stats_reconcile import MAX_OBSERVATIONS
                while len(self.stats_observations)>MAX_OBSERVATIONS:self.stats_observations.pop(next(iter(self.stats_observations)))
        finally:self.stats_work_running=False

    async def connection(self, reader, writer):
        task = asyncio.current_task(); self.connections.add(task)
        try:
            sock = writer.get_extra_info('socket')
            _, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, self.config['uid']): raise ProjectFault('Agent coordinator access denied.', 403)
            raw = await asyncio.wait_for(reader.readline(), 10)
            if len(raw) > 131072: raise ProjectFault('Agent request too large.', 400)
            result = await self.handle(json.loads(raw))
            writer.write((encode({'result': result}) + '\n').encode())
        except ProjectFault as e:
            writer.write((encode({'error': str(e), 'code': e.code}) + '\n').encode())
        except Exception:
            writer.write(b'{"error":"The agent coordinator is unavailable.","code":503}\n')
        finally:
            try: await writer.drain()
            except Exception: pass
            writer.close()
            try: await writer.wait_closed()
            except Exception: pass
            self.connections.discard(task)


async def main():
    os.umask(0o077)
    config = json.loads(Path('/etc/r4os-studio-agents/config.json').read_text())
    if os.getuid() != config['uid']: raise SystemExit('Run the coordinator as its configured service user.')
    host = Host(config); await host.recover()
    runtime = directory('/run/r4os-studio-agents')
    path = runtime / 'host.sock'
    if path.exists(): path.unlink()
    server = await asyncio.start_unix_server(host.connection, path=str(path), limit=131073)
    path.chmod(0o600)
    stopped = asyncio.Event(); loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, stopped.set)
    replacement = None
    async def maintain():
        nonlocal replacement
        while not stopped.is_set():
            try:
                async with host.lock:
                    await host.refresh()
                    await host.dispatch_queues()
                    from goal_keepalive_host import schedule as schedule_goals
                    schedule_goals(host)
                    from skill_source_host import dispatch as dispatch_sources
                    await dispatch_sources(host)
                    target = Path('/opt/r4os-studio/current').resolve(strict=True)
                    if not host.active and not host.unbound and not host.goal_tasks and not host.message_tasks and not host.skill_delete_tasks and not host.session_delete_tasks and not host.attachment_decodes and not host.catalog_tasks and not host.source_tasks and not host.claude_auth.busy and not host.plan_login.busy and not host.claude_probe_lock.locked() and not host.catalog_lock.locked() and not host.goal_readback_lock.locked() and not host.image_capability_lock.locked() and not host.read_work.pending and target != Path(__file__).resolve().parents[2]:
                        release_protocol(target)
                        script = target / 'scripts/agent-sessions/host.py'
                        if not target.is_relative_to('/opt/r4os-studio/releases') or script.stat().st_uid != 0 or script.stat().st_mode & 0o022:
                            raise ValueError('Invalid coordinator release.')
                        replacement = script; stopped.set()
            except Exception: pass  # Preserve current workers and retry, never infer a new job.
            try:
                await host.reconcile_statistics()
            except Exception:pass  # Numeric capture failure cannot steer runs.
            try: await asyncio.wait_for(stopped.wait(), 2)
            except asyncio.TimeoutError: pass
    monitor = asyncio.create_task(maintain())
    async with server: await stopped.wait()
    await host.claude_auth.close()
    monitor.cancel(); await asyncio.gather(monitor, return_exceptions=True)
    if host.connections:
        try: await asyncio.wait_for(asyncio.gather(*host.connections, return_exceptions=True), 25)
        except asyncio.TimeoutError: pass
    await host.read_work.close()
    if replacement: os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(replacement)])


if __name__ == '__main__': asyncio.run(main())
