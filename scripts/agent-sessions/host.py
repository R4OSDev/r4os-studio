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

from profile import write_json, directory
from session_store import SessionStore, identity, encode
from run_store import admit, get_run, transition, events
from protocol import release_protocol, supported_profiles, validate_release
from store import ProjectFault
from owner import binding, owners, skills_root

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
        self.root = directory(Path(config['projects']) / '.studio/agents')
        self.lock = asyncio.Lock(); self.active = {}; self.unbound = set(); self.connections = set(); self.goal_tasks = {}
        self.goal_readback_lock = asyncio.Lock()
        self.image_capability_lock=asyncio.Lock()
        self.inboxes=set()
        self.message_tasks={}

    def store(self, ident, kind='project'): return SessionStore(self.config['projects'], self.config['r4os'], ident, kind)

    async def active_unit(self, run_id):
        state = await systemctl('show', UNIT.format(identity(run_id)), '--property=ActiveState', '--value')
        return state in ('active', 'activating', 'deactivating', 'reloading')

    async def goal_worker_matches(self, meta, row):
        if not json.loads(row['config']).get('goalExecution'):return True
        try:
            pid=int(await systemctl('show',UNIT.format(row['id']),'--property=MainPID','--value'))
            if pid<=0 or (Path('/proc')/str(pid)).stat().st_uid!=self.config['uid']:return False
            worker=json.loads(row['worker'] or '{}')
            if not worker:return row['state']=='queued'
            birth=(Path('/proc')/str(pid)/'stat').read_text().rsplit(') ',1)[1].split()[19]
            return (worker.get('pid')==pid and worker.get('birth')==birth and worker.get('release')==meta['release']
                and (Path('/proc')/str(pid)).stat().st_uid==self.config['uid'])
        except (OSError,ValueError,KeyError,IndexError):return False

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
                live_plays={json.loads(r['config']).get('goalExecution',{}).get('requestId')
                    for r in store.db.execute('SELECT * FROM runs WHERE busy=1') if r['id'] in self.active}
                Goals(store).recover(live_plays)
                # Repair stale pending cards from earlier compatible releases
                # using confirmed receipts, without replaying any tool operation.
                finished = set()
                for row in store.db.execute('SELECT i.run_id,i.payload FROM items i JOIN runs r ON r.id=i.run_id WHERE r.busy=0'):
                    if json.loads(row['payload']).get('status') in ('pending', 'running'): finished.add(row['run_id'])
                for run_id in finished:
                    from worker import reconcile_items
                    reconcile_items(store, run_id, get_run(store, run_id)['state'])
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
                self.active.pop(run_id, None)
            finally: store.close()
        await self.check_unbound()

    async def handle(self, request):
        op = request.get('operation')
        if op == 'capabilities': return {'enabled': not bool(self.unbound), 'protocol': 1, 'sessionMessages': 1, 'messageQueue': 1, 'messageSteering': 1, 'runReceipts': 1, 'nativeGoals': 1, 'nativeGoalExecution': 2, 'nativeGoalReadback': 1, 'nativeImageInputs': 1, 'documentInputs': 1, 'imageGenerationSettings':1, 'projectDeletionLocks': 1, 'projectInstructions': 1, 'vmStartTools': 1, 'skillSessions': 1, 'skillAuthorTools': 1, 'globalSkills': 1, 'skillScripts': 1, 'nativeWebSearch': 1, 'roadmapSettings': 1, 'roadmapTools': 1, 'remoteHostTools': 1, 'maxActiveRuns': self.config.get('maxActiveRuns', 2), 'version': json.loads((Path(__file__).resolve().parents[2] / 'shared/version.json').read_text())['version']}
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
        if op in ('messages', 'message_receipt', 'submit_message', 'message_control'):
            from message_store import Messages
            capability = None
            if op == 'submit_message' and request.get('input',{}).get('mode') != 'steer':
                preliminary = self.store(project_id, kind)
                try:
                    selected = preliminary.get(session_id)
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
                        async with self.image_capability_lock: capability = await inspect(preliminary, session_id, self.config['providers'])
                finally: preliminary.close()
            async with self.lock:
                if op == 'message_control': await self.refresh()
                store = self.store(project_id, kind)
                try:
                    store.row(session_id)
                    messages = Messages(store)
                    if op == 'messages': return messages.snapshot(session_id, request.get('before'), request.get('view','all'))
                    if op == 'message_receipt': return messages.receipt(session_id, request['requestId'])
                    self.inboxes.add((kind, project_id, session_id))
                    if op == 'message_control': return messages.control(session_id, request['input'])
                    flags = {'nativeWebSearch':1,'skillSelection':1,'skillScripts':1,'nativeImageInputs':1,'documentInputs':1,'imageGenerationSettings':1,
                             **({'projectInstructions':1,'roadmapSettings':1,'remoteHostTools':1} if kind=='project' else {})}
                    if store.db.execute('SELECT 1 FROM session_messages WHERE request_id=?', (request['input'].get('requestId'),)).fetchone():
                        # An original receipt outlives its active worker/turn.
                        # Compare the immutable input before checking fresh targets.
                        return messages.accept(session_id, request['input'], self.config['providers'], flags, capability)[0]
                    if request['input'].get('mode') == 'steer':
                        meta = self.active.get(request['input'].get('target',{}).get('runId'))
                        if not meta or binding(meta)!=(kind,project_id) or meta['sessionId']!=session_id:
                            raise ProjectFault('The direct target has no confirmed original worker binding.',409)
                        validate_release(meta)
                        original = get_run(store, request['input']['target']['runId'])
                        if json.loads(original['worker'] or '{}').get('release') != meta['release']:
                            raise ProjectFault('The direct target no longer has its original worker release.',403)
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
            from goal_readback import readback
            if self.goal_readback_lock.locked():raise ProjectFault('Another native Goal readback is in progress.',429)
            async with self.goal_readback_lock:
                store=self.store(project_id,kind)
                try:return await asyncio.wait_for(readback(store,session_id),15)
                finally:store.close()
        if op in ('goal', 'goal_receipt', 'goal_command'):
            from goal_store import Goals
            async with self.lock:
                store = self.store(project_id, kind)
                try:
                    goals = Goals(store)
                    if op == 'goal': return goals.snapshot(session_id)
                    if op == 'goal_receipt': return goals.receipt(session_id, identity(request['requestId']))
                    if self.unbound: raise ProjectFault('Reconcile the original unbound workers before changing a Goal.',503)
                    if len(self.goal_tasks) >= 2: raise ProjectFault('Goal controls are busy. Read the original request before retrying.',429)
                    result, fresh = goals.accept(session_id, request['input'])
                    if request['input'].get('action') in ('pause','stop'):
                        from message_store import Messages
                        Messages(store).hold(session_id, 'The user paused or stopped this session. Continue explicitly.')
                    if fresh:
                        key=(kind,project_id,session_id,result['requestId'])
                        task=asyncio.create_task(self.goal_command(*key)); self.goal_tasks[key]=task
                        task.add_done_callback(lambda _, key=key: self.goal_tasks.pop(key,None))
                    return result
                finally: store.close()
        if op == 'run_receipt':
            store = self.store(project_id,kind)
            try:
                store.row(session_id)
                row = store.db.execute('SELECT * FROM runs WHERE session_id=? AND request_id=?',(session_id,identity(request['requestId']))).fetchone()
                if not row: raise ProjectFault('Original run request not found.',404)
                return store.run_present(row)
            finally: store.close()
        if op == 'events':
            store = self.store(project_id, kind)
            try: return events(store, session_id, request.get('after', 0))
            finally: store.close()
        if op == 'stop_run':
            async with self.lock: return await self.stop(project_id, session_id, identity(request['runId']), kind)
        if op == 'start_run':
            image_capability=None
            if request.get('input',{}).get('imageGenerationSettings')==1:
                preliminary=self.store(project_id,kind)
                try:
                    previous=preliminary.db.execute('SELECT 1 FROM runs WHERE request_id=?',(request['input'].get('requestId'),)).fetchone()
                    selected=preliminary.get(session_id)
                    if not previous and selected.get('imageGenerationEnabled',True):
                        from image_generation import inspect
                        if self.image_capability_lock.locked():raise ProjectFault('An image capability read is in progress. No run was started; try again shortly.',429)
                        async with self.image_capability_lock:image_capability=await inspect(preliminary,session_id,self.config['providers'])
                finally:preliminary.close()
            async with self.lock:
                await self.refresh()
                if self.unbound: raise ProjectFault('An agent worker has no confirmed binding. Restore host support before starting another run.', 503)
                store = self.store(project_id, kind)
                try:
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
                        if not target.is_relative_to('/opt/r4os-studio/releases') or not (target/'scripts/agent-sessions/goal_worker.py').is_file():
                            raise ProjectFault('This worker release has no native multi-turn Goal support.',503)
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
                    if not previous and len(self.active) >= self.config.get('maxActiveRuns', 2):
                        raise ProjectFault('The host is already running its maximum number of agent runs.')
                    run, fresh = admit(store, session_id, request['input'], self.config['providers'],image_capability)
                    if not fresh: return run
                    return await self.launch_admitted(store, run, kind, project_id, session_id)
                finally: store.close()
        raise ProjectFault('Unsupported agent coordinator operation.', 400)

    async def launch_admitted(self, store, run, kind, project_id, session_id):
        try:
            release = Path(self.config.get('workerReleaseRoot', '/opt/r4os-studio/current')).resolve(strict=True)
            if not release.is_relative_to('/opt/r4os-studio/releases'): raise ProjectFault('Invalid agent worker release.', 503)
            release_protocol(release)
            if not (release / 'scripts/agent-sessions/instructions.py').is_file():
                raise ProjectFault('This worker release cannot apply project instructions.', 503)
            if store.get(session_id)['engine']['profile'] not in supported_profiles(release): raise ProjectFault('This conversation needs a newer Studio release; its native thread was preserved.', 409)
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
            Messages(store).finish(sid,request_id,state,'The original direct worker receipt could not be confirmed. No message was submitted again.')
            if isinstance(error,asyncio.CancelledError): raise
        finally: store.close()

    async def dispatch_queues(self):
        from message_store import Messages
        if self.unbound or len(self.active) >= self.config.get('maxActiveRuns', 2): return
        for kind, ident, sid in tuple(self.inboxes):
            if len(self.active) >= self.config.get('maxActiveRuns', 2): return
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
                from goal_store import Goals, pending
                goal = Goals(store).snapshot(sid)
                if pending(store) or goal['phase'] not in ('idle',): continue
                if goal['goal'] and goal['goal']['status'] == 'active':
                    messages.hold(sid, 'Pause the original Goal before continuing this queue.'); continue
                config = frozen['config']
                run, fresh = admit(store, sid, frozen['runInput'], self.config['providers'], config.get('imageGenerationCapability'), config)
                if not fresh:
                    messages.hold(sid, 'The original queued run already exists. Inspect its receipt; it was not started again.'); continue
                await self.launch_admitted(store, run, kind, ident, sid)
            except Exception as error:
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
            if data['action']=='play':
                session=store.get(sid)
                goals.stage(sid,rid,'admitting_worker')
                try:
                    run=await self.handle({'operation':'start_run','ownerType':kind,'ownerId':project_id,'sessionId':sid,
                        'input':{'mode':'goal','goalRequestId':rid,'requestId':rid,'revision':session['revision'],
                            'nativeWebSearch':1,'skillSelection':1,'skillScripts':1,'nativeImageInputs':1,'documentInputs':1,'imageGenerationSettings':1,
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
                row = get_run(store, run_id)
                if row['busy']: transition(store, run_id, 'interrupted', 'Run stopped.')
            self.active.pop(run_id, None)
            self.unbound.discard(run_id)
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
                    target = Path('/opt/r4os-studio/current').resolve(strict=True)
                    if not host.active and not host.unbound and not host.goal_tasks and not host.message_tasks and not host.goal_readback_lock.locked() and not host.image_capability_lock.locked() and target != Path(__file__).resolve().parents[2]:
                        release_protocol(target)
                        script = target / 'scripts/agent-sessions/host.py'
                        if not target.is_relative_to('/opt/r4os-studio/releases') or script.stat().st_uid != 0 or script.stat().st_mode & 0o022:
                            raise ValueError('Invalid coordinator release.')
                        replacement = script; stopped.set()
            except Exception: pass  # Preserve current workers and retry, never infer a new job.
            try: await asyncio.wait_for(stopped.wait(), 2)
            except asyncio.TimeoutError: pass
    monitor = asyncio.create_task(maintain())
    async with server: await stopped.wait()
    monitor.cancel(); await asyncio.gather(monitor, return_exceptions=True)
    if host.connections:
        try: await asyncio.wait_for(asyncio.gather(*host.connections, return_exceptions=True), 25)
        except asyncio.TimeoutError: pass
    if replacement: os.execv('/usr/bin/python3', ['/usr/bin/python3', '-B', str(replacement)])


if __name__ == '__main__': asyncio.run(main())
