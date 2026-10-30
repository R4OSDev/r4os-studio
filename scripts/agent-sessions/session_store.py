from skill_lifecycle import guarded,initialize
"""Bounded project session catalog. Fixed operations, never arbitrary SQL or paths."""
import datetime
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import uuid

sys.path.append(str(Path(__file__).resolve().parents[1] / 'projects'))
from store import connect as project_connect, operation as project_operation, ProjectFault
from layout import workspace, folder
from profile import CODEX_VERSION, CODEX_SHA256, PROFILE, NOTES_SKILL_PROFILE, SKILL_PROFILES, permission_tools, default_enabled
from owner import owner_type, binding, skill_workspace
import skill_preferences

TOOL_IDS = tuple('studio.' + name for name in permission_tools(PROFILE))
TERMINAL_STATES = ('completed', 'failed', 'interrupted')


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise ProjectFault('Invalid session identity.', 400)
    return value


def encode(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def text(value, maximum, empty=False):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ProjectFault('Invalid session text.', 400)
    value = value.strip()
    if not value and not empty: raise ProjectFault('Enter a session name.', 400)
    return value


def providers(directory):
    file = Path(directory) / 'providers.json'
    values=[]
    if file.exists():
        if file.resolve(strict=True) != file.absolute() or not file.is_file():
            raise ProjectFault('Provider storage is unavailable.', 503)
        values=json.loads(file.read_text())
    result=[v for v in values if v.get('type') == 'openai' and v.get('connected') is True]
    # API storage availability never rewrites or disables a subscription.
    from api_provider_store import ApiProviders
    try:
        legacy={v.get('id') for v in values}
        result += [v for v in ApiProviders(directory).listing() if v['enabled'] and v['id'] not in legacy]
    except ProjectFault:pass
    from claude_provider_store import ClaudeProviders
    try:
        known={v.get('id') for v in values+result}
        result += [v for v in ClaudeProviders(directory).listing() if v['status']=='connected' and v['id'] not in known]
    except ProjectFault:pass
    return result


def provider_models(directory, provider_id):
    identity(provider_id)
    source = Path(directory) / provider_id / 'models_cache.json'
    from claude_auth_store import AuthStore
    from claude_provider_store import ClaudeProviders
    try:native=next((v for v in ClaudeProviders(directory).listing() if v['id']==provider_id),None) if not source.exists() else None
    except ProjectFault:native=None
    if native:
        try:catalog=AuthStore(directory).latest_catalog(provider_id)
        except ProjectFault:return []
        if not catalog:return []
        return [{'id':m['id'],'name':m['name'],'imageInputs':m['imageInputs'],'inputModalities':m['inputModalities'],
            'efforts':m['efforts'],'defaultEffort':m['defaultEffort'],'fastModeAvailable':False,'available':False,
            'unavailableReasons':m['unavailableReasons'],'contextWindow':None,
            'source':{'kind':'metadata','recordedAt':catalog['receivedAt']}} for m in catalog['models']]
    try:
        # Existing subscription homes remain authoritative for their UUID.
        if source.exists():
            if source.resolve(strict=True) != source.absolute() or not source.is_file(): raise ValueError()
            values = json.loads(source.read_text())['models']
        else:
            from api_models import connection,catalog
            provider=connection(directory,provider_id)
            values=catalog(directory,provider) if provider else []
    except (OSError, ValueError, KeyError, ProjectFault):
        return []
    result = []
    from image_inputs import model_images,model_modalities
    for m in sorted(values, key=lambda m: m.get('priority', 999)):
        if m.get('visibility') != 'list': continue
        efforts = [x['effort'] for x in m.get('supported_reasoning_levels', [])]
        if not efforts: efforts = [m.get('default_reasoning_level', 'low')]
        result.append({'id': m['slug'], 'name': m.get('display_name') or m['slug'],
                       'imageInputs': model_images(m),
                       'inputModalities': model_modalities(m),
                       'efforts': efforts, 'defaultEffort': m.get('default_reasoning_level') or efforts[0],
                       'fastModeAvailable': any(isinstance(tier, dict) and tier.get('id') in ('fast', 'priority')
                                                for tier in (m.get('service_tiers') or []))
                           or 'fast' in (m.get('additional_speed_tiers') or [])})
    return result


def options(provider_dir, r4os, selected_profile=PROFILE):
    values = []
    for v in providers(provider_dir):
        reason=None
        models=provider_models(provider_dir,v['id'])
        if v.get('type')=='api':
            from api_catalog import Catalogs
            try:catalog=Catalogs(provider_dir).listing(v['id'])
            except (ProjectFault,OSError,ValueError,TypeError,KeyError):
                catalog={'models':[]};models=[];reason='This API model catalog is unavailable. Review this connection in System settings.'
            if catalog['models']:
                models=[{'id':m['id'],'name':m['name'],'efforts':m['efforts'],'defaultEffort':m['defaultEffort'] or '',
                    'fastModeAvailable':False,'imageInputs':'unsupported','inputModalities':['text'],
                    'available':m['available'] and not catalog['stale'],
                    'unavailableReasons':['Model facts belong to earlier connection settings.'] if catalog['stale'] else m['unavailableReasons'],
                    'contextWindow':m['contextWindow'],'source':m['source']} for m in catalog['models']]
        if v.get('type')=='claude-subscription':reason='Claude subscription model execution is not available in this Studio version yet.'
        values.append({'id': v['id'], 'name': v['name'], 'type':v['type'],'models':models,**({'unavailableReason':reason} if reason else {})})
    return {'providers': values, 'tools': [{'id': 'studio.' + v, 'defaultEnabled': default_enabled(v)} for v in permission_tools(selected_profile)],
            'nativeTools': [{'id': 'web_search', 'defaultEnabled': True},{'id':'image_generation','defaultEnabled':True}],
            'engine': engine(r4os, selected_profile)}


def engine(r4os, selected_profile=PROFILE):
    from profile import regular, digest
    value = {'profile': selected_profile, 'version': CODEX_VERSION, 'sha256': CODEX_SHA256, 'available': False}
    try:
        selected = json.loads((Path(r4os) / 'Profiles/versions.json').read_text())['defaults']['codex']
        binary = Path(r4os) / 'Toolchains/Codex' / CODEX_VERSION / 'codex'
        if selected['version'] != CODEX_VERSION or Path(selected['binary']) != binary or digest(regular(binary)) != CODEX_SHA256:
            raise ValueError()
        value['available'] = True
    except (OSError, ValueError, KeyError):
        value['reason'] = 'Select the qualified Codex 0.163.0 installation in Updates before creating an agent session.'
    return value


def validate_settings(data, provider_dir):
    text(data['name'], 120)
    candidate = next((v for v in providers(provider_dir) if v['id'] == data['providerId']), None)
    if candidate is None: raise ProjectFault('Connect the selected provider before saving these settings.', 409)
    if candidate.get('type')=='api' and (data.get('webSearchEnabled',False) or data.get('imageGenerationEnabled',False) or data.get('fastMode',False)):
        raise ProjectFault('Hosted web/image generation and Fast Mode are not qualified for this API model.',409)
    if candidate.get('type')=='claude-subscription' and (data.get('webSearchEnabled',False) or data.get('imageGenerationEnabled',False) or data.get('fastMode',False)):
        raise ProjectFault('Hosted web/image generation and Fast Mode are unavailable for this native Claude adapter.',409)
    model = next((m for m in provider_models(provider_dir, data['providerId']) if m['id'] == data['model']), None)
    if model is None or data['effort'] not in model['efforts']:
        raise ProjectFault('Select an available model and reasoning effort.', 400)
    if candidate.get('type')=='claude-subscription' and model.get('available') is False:
        raise ProjectFault('Claude subscription model execution is not available in this Studio version yet.',409)
    if type(data.get('fastMode', False)) is not bool:
        raise ProjectFault('Invalid Fast Mode setting.', 400)
    if type(data.get('webSearchEnabled', True)) is not bool:
        raise ProjectFault('Invalid Web search setting.', 400)
    if type(data.get('environmentNotesEnabled',True)) is not bool:raise ProjectFault('Invalid Environment notes setting.',400)
    if type(data.get('imageGenerationEnabled',True)) is not bool:raise ProjectFault('Invalid Image generation setting.',400)
    if type(data.get('roadmapEnabled', True)) is not bool:
        raise ProjectFault('Invalid Roadmap setting.', 400)
    if data.get('fastMode', False) and not model['fastModeAvailable']:
        raise ProjectFault('Fast Mode is unavailable for the selected model.', 400)
    if not isinstance(data['permissions'], dict) or set(data['permissions']) != {'studio.' + t for t in permission_tools(data.get('engine', {}).get('profile', PROFILE))} or any(type(v) is not bool for v in data['permissions'].values()):
        raise ProjectFault('Invalid tool permissions.', 400)


class SessionStore:
    @initialize
    def __init__(self, projects, r4os, project_id, kind='project'):
        from project_use import acquire
        self.owner_type = owner_type(kind); self.owner_id = identity(project_id)
        self.selected_profile = NOTES_SKILL_PROFILE if kind == 'skill' else PROFILE
        self.session_uses = {}
        self.project_use = acquire(projects, project_id) if kind == 'project' else None
        try: self.open(projects, r4os, project_id)
        except BaseException:
            if self.project_use: self.project_use.close()
            raise

    def open(self, projects, r4os, project_id):
        self.projects, self.r4os, self.project_id = Path(projects), Path(r4os), identity(project_id)
        if self.owner_type == 'project':
            with closing(project_connect(self.projects)) as db:
                self.project = project_operation(db, {'operation': 'get', 'id': project_id}, self.r4os)
            self.workspace = workspace(self.projects, project_id, require_current=True)
        else:
            self.project = None
            self.workspace = skill_workspace(self.projects, project_id)
        self.directory = self.workspace.parent / 'Sessions'
        self.directory.mkdir(mode=0o700, exist_ok=True); folder(self.directory)
        path = self.directory / 'Sessions.sqlite'
        for f in (path, path.with_name(path.name + '-journal')):
            if f.exists() or f.is_symlink():
                if not stat.S_ISREG(f.lstat().st_mode): raise ProjectFault('Invalid session database.', 503)
        self.db = sqlite3.connect(path, timeout=5)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('BEGIN IMMEDIATE')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1): raise ProjectFault('Unsupported session data version.', 503)
        if version == 0:
            with self.db:
                if self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ProjectFault('Unrecognized session database.', 503)
                schema = '''
CREATE TABLE sessions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
 settings TEXT NOT NULL, engine TEXT NOT NULL, thread_id TEXT, revision INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE requests(request_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload_hash TEXT NOT NULL,
 session_id TEXT NOT NULL REFERENCES sessions(id), response TEXT NOT NULL);
CREATE TABLE runs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 request_id TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL, state TEXT NOT NULL, busy INTEGER NOT NULL,
 config TEXT NOT NULL, turn_id TEXT, worker TEXT, error TEXT, created_at TEXT NOT NULL, completed_at TEXT);
CREATE UNIQUE INDEX one_active_project_run ON runs(busy) WHERE busy=1;
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES sessions(id),
 run_id TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX session_event_cursor ON events(session_id, seq);
CREATE TABLE items(session_id TEXT NOT NULL REFERENCES sessions(id), run_id TEXT NOT NULL,
 item_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(session_id, run_id, item_id));
CREATE TABLE tools(run_id TEXT NOT NULL REFERENCES runs(id), call_id TEXT NOT NULL, tool TEXT NOT NULL,
 arguments_hash TEXT NOT NULL, state TEXT NOT NULL, intent TEXT NOT NULL, result TEXT,
 PRIMARY KEY(run_id, call_id));
PRAGMA user_version=1;
'''
                for statement in schema.split(';'):
                    if statement.strip(): self.db.execute(statement)
        self.db.commit()

    def close(self):
        self.db.close()
        for use in self.session_uses.values():
            if use is not None: use.close()
        if self.project_use: self.project_use.close()

    def row(self, session_id):
        from session_lifetime import acquire, state
        session_id = identity(session_id)
        if session_id not in self.session_uses:
            self.session_uses[session_id] = acquire(self.projects, self.owner_type, self.owner_id, session_id)
        retired = state(self.db, session_id)
        if retired:
            raise ProjectFault('This session was deleted.' if retired[0] == 'deleted' else 'Session cleanup is in progress. Read the original deletion receipt.', 410 if retired[0] == 'deleted' else 409)
        row = self.db.execute('SELECT * FROM sessions WHERE id=? AND project_id=?',
                              (identity(session_id), self.project_id)).fetchone()
        if row is None: raise ProjectFault('Session not found.', 404)
        return row

    def present(self, row):
        settings = json.loads(row['settings'])
        settings.setdefault('fastMode', False)
        settings.setdefault('webSearchEnabled', True)
        settings.setdefault('imageGenerationEnabled',True)
        settings.setdefault('environmentNotesEnabled',True)
        if self.owner_type == 'project':
            settings.setdefault('roadmapEnabled', True)
        else:
            settings.pop('roadmapEnabled', None)
        latest = self.db.execute('SELECT * FROM runs WHERE session_id=? ORDER BY created_at DESC LIMIT 1', (row['id'],)).fetchone()
        engine = json.loads(row['engine'])
        from session_context import read as context_read
        context=context_read(self,row)
        from environment_note_tools import availability
        settings['environmentNotesAccess'] = availability(engine.get('profile'))
        if self.owner_type == 'project':
            from roadmap_access import availability
            settings['roadmapAccess'] = availability(engine.get('profile'))
            from remote_context import availability as remote_availability
            settings['remoteHostAccess'] = remote_availability(self, engine.get('profile'))
        if self.owner_type == 'skill' and engine.get('profile') not in SKILL_PROFILES:
            raise ProjectFault('This skill session has an incompatible tool profile. Its history was preserved.', 409)
        return {'id': row['id'], 'owner': {'type': self.owner_type, 'id': self.owner_id},
                ('skillId' if self.owner_type == 'skill' else 'projectId'): row['project_id'], 'name': row['name'], **settings,
                'engine': engine, 'context':context, 'revision': row['revision'],
                'skillOverrides': skill_preferences.read(self.projects, self.owner_type, self.owner_id, row['id']),
                'createdAt': row['created_at'], 'updatedAt': row['updated_at'],
                'latestRun': self.run_present(latest) if latest else None}

    def list(self):
        from session_lifetime import state
        return [self.present(r) for r in self.db.execute('SELECT * FROM sessions WHERE project_id=? ORDER BY updated_at DESC,id', (self.owner_id,)) if not state(self.db, r['id'])]

    def get(self, session_id): return self.present(self.row(session_id))

    @guarded
    def create(self, data, provider_dir):
        if set(data) - {'fastMode'} != {'name', 'providerId', 'model', 'effort', 'requestId'}:
            raise ProjectFault('Unexpected session fields.', 400)
        key = identity(data['requestId']); payload_hash = hashlib.sha256(encode(data).encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='retired_session_requests'").fetchone():
                retired = self.db.execute('SELECT payload_hash FROM retired_session_requests WHERE request_id=?', (key,)).fetchone()
                if retired:
                    raise ProjectFault('This session creation request was retired after deletion.' if retired[0] == payload_hash else 'This request ID belongs to another original submission.', 410 if retired[0] == payload_hash else 409)
            old = self.db.execute('SELECT * FROM requests WHERE request_id=?', (key,)).fetchone()
            if old:
                if old['kind'] != 'create' or old['payload_hash'] != payload_hash:
                    raise ProjectFault('This request ID belongs to another session submission.')
                return self.get(old['session_id'])
            if self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] >= 200:
                raise ProjectFault('The session limit for this workspace has been reached.')
            settings = {k: data[k] for k in ('providerId', 'model', 'effort')}
            settings['fastMode'] = data.get('fastMode', False)
            settings['webSearchEnabled'] = True
            settings['imageGenerationEnabled']=True
            settings['environmentNotesEnabled']=True
            selected=next((v for v in providers(provider_dir) if v['id']==settings['providerId']),None)
            api=selected if selected and selected.get('type')=='api' else None
            claude=selected if selected and selected.get('type')=='claude-subscription' else None
            if api or claude:
                settings['webSearchEnabled']=False;settings['imageGenerationEnabled']=False
            if self.owner_type == 'project': settings['roadmapEnabled'] = True
            from tool_defaults import permissions as creation_permissions
            settings['permissions'] = creation_permissions(self)
            validate_settings({**settings, 'name': data['name'], 'engine': {'profile': self.selected_profile}}, provider_dir)
            ident, created = str(uuid.uuid4()), now()
            selected_engine = engine(self.r4os, self.selected_profile)
            if claude:
                from claude_selection import engine as claude_engine
                selected_engine=claude_engine(provider_dir,self.selected_profile)
            if api:selected_engine['api']={'providerId':api['id'],'baseUrl':api['baseUrl'],'protocol':api['protocol'],
                'server':api.get('server','custom')}
            if not selected_engine['available']: raise ProjectFault(selected_engine['reason'])
            self.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,?,?)',
                            (ident, self.project_id, text(data['name'], 120), encode(settings), encode(selected_engine), created, created))
            from goal_total import mark_new
            mark_new(self, ident)
            if claude:
                from claude_history import ClaudeHistory
                ClaudeHistory(self,ident).create(claude)
            value = self.get(ident)
            self.db.execute('INSERT INTO requests VALUES (?,?,?,?,?)', (key, 'create', payload_hash, ident, encode(value)))
            self.db.commit()
            return value
        finally:
            if self.db.in_transaction: self.db.rollback()

    @guarded
    def update(self, session_id, data, provider_dir):
        if not set(data).issubset({'revision', 'name', 'providerId', 'model', 'effort', 'fastMode', 'permissions', 'skillOverrides', 'webSearchEnabled', 'imageGenerationEnabled', 'environmentNotesEnabled', 'roadmapEnabled'}) or type(data.get('revision')) is not int:
            raise ProjectFault('Unexpected session settings.', 400)
        if 'roadmapEnabled' in data and (self.owner_type != 'project' or type(data['roadmapEnabled']) is not bool):
            raise ProjectFault('Roadmap is a boolean setting for project sessions only.', 400)
        if 'fastMode' in data and type(data['fastMode']) is not bool:
            raise ProjectFault('Invalid Fast Mode setting.', 400)
        if 'environmentNotesEnabled' in data and type(data['environmentNotesEnabled']) is not bool:raise ProjectFault('Invalid Environment notes setting.',400)
        if 'imageGenerationEnabled' in data and type(data['imageGenerationEnabled']) is not bool:raise ProjectFault('Invalid Image generation setting.',400)
        if 'webSearchEnabled' in data and type(data['webSearchEnabled']) is not bool:
            raise ProjectFault('Invalid Web search setting.', 400)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous = self.get(session_id)
            if data.get('providerId',previous['providerId'])!=previous['providerId']:
                new_api=any(v['id']==data['providerId'] and v.get('type')=='api' for v in providers(provider_dir))
                new_claude=any(v['id']==data['providerId'] and v.get('type')=='claude-subscription' for v in providers(provider_dir))
                if previous['engine'].get('kind')=='claude-code' or new_claude:
                    raise ProjectFault('Changing the native Claude provider requires a new session. This conversation was preserved.',409)
                if previous['engine'].get('api') or new_api:
                    raise ProjectFault('Changing API connection requires a new session. This conversation was preserved.',409)
            if previous['revision'] != data['revision']: raise ProjectFault('Session settings changed. Reload before saving.')
            if self.db.execute('SELECT 1 FROM runs WHERE session_id=? AND busy=1', (session_id,)).fetchone():
                raise ProjectFault('Stop or resolve the current run before changing session settings.')
            from goal_store import pending
            if pending(self): raise ProjectFault('Wait for the original Goal control before changing session settings.', 409)
            value = {**previous, **data}
            settings = {k: value[k] for k in ('providerId', 'model', 'effort', 'fastMode', 'permissions', 'webSearchEnabled', 'imageGenerationEnabled', 'environmentNotesEnabled')}
            if self.owner_type == 'project': settings['roadmapEnabled'] = value['roadmapEnabled']
            choices = skill_preferences.normalize(value['skillOverrides'])
            skill_change = choices != previous['skillOverrides']
            value['name'] = text(value['name'], 120)
            changed = value['name'] != previous['name'] or any(value[k] != previous[k] for k in settings) or skill_change
            if changed:
                # Name-only edits stay possible when a formerly connected provider disappears.
                if any(value[k] != previous[k] for k in settings): validate_settings(value, provider_dir)
                if skill_change: skill_preferences.write(self, session_id, choices)
                self.db.execute('UPDATE sessions SET name=?,settings=?,revision=revision+1,updated_at=? WHERE id=?',
                                (text(value['name'], 120), encode(settings), now(), session_id))
            self.db.commit(); return self.get(session_id)
        finally:
            if self.db.in_transaction: self.db.rollback()

    def history(self, session_id, before=None, limit=50):
        self.row(session_id)
        if type(limit) is not int or not 1 <= limit <= 100: raise ProjectFault('Invalid history page.', 400)
        self.db.execute('BEGIN')
        rows = self.db.execute('SELECT rowid,* FROM items WHERE session_id=? AND rowid < ? ORDER BY rowid DESC LIMIT ?',
                               (session_id, before or 9223372036854775807, limit + 1)).fetchall()
        batch = []; size = 0
        for row in rows[:limit]:
            next_size = len(row['payload'].encode())
            if batch and size + next_size > 512*1024: break
            batch.append(row); size += next_size
        more = len(rows) > len(batch); rows = batch
        cursor = rows[-1]['rowid'] if more else None
        event_cursor = self.db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE session_id=?', (session_id,)).fetchone()[0]
        self.db.commit()
        return {'items': [json.loads(r['payload']) for r in reversed(rows)], 'before': cursor, 'cursor': event_cursor}

    def run_present(self, r):
        thread = self.row(r['session_id'])['thread_id']
        worker = json.loads(r['worker'] or '{}')
        from provider_retry import snapshot as retry_snapshot
        retry = retry_snapshot(self, r)
        support = r['state']=='running' and bool(thread and r['turn_id']) and worker.get('messageProtocol')==1 and worker.get('messageTurnActive') is True
        activation=None
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='goal_activations'").fetchone():
            saved=self.db.execute('SELECT a.request_id,c.state FROM goal_activations a JOIN goal_commands c USING(request_id) WHERE a.run_id=? ORDER BY a.created_at DESC,a.rowid DESC LIMIT 1',(r['id'],)).fetchone()
            if saved: activation={'requestId':saved['request_id'],'state':saved['state']}
        return {'id': r['id'], 'sessionId': r['session_id'], 'state': r['state'], 'error': r['error'],
                **({'providerRetry': retry} if retry else {}),
                'threadId':thread,'turnId':r['turn_id'],'messageSupport':support,
                'goalControlSupport':r['state']=='running' and bool(thread and r['turn_id']) and worker.get('liveGoalControl')==1 and worker.get('liveGoalOpen') is True,
                **({'goalActivation':activation} if activation else {}),
                **({'mode':'goal'} if json.loads(r['config']).get('goalExecution') else {}),
                'owner': {'type': self.owner_type, 'id': self.owner_id},
                'createdAt': r['created_at'], 'completedAt': r['completed_at']}


def operation(projects, r4os, provider_dir, request):
    kind, ident = binding(request)
    if request.get('operation') == 'options':
        # Validate project identity/layout, even for a read-only options request.
        store = SessionStore(projects, r4os, ident, kind)
        try:
            result = options(provider_dir, r4os, store.selected_profile)
            from tool_defaults import permissions as creation_permissions
            defaults = creation_permissions(store)
            result['tools'] = [{'id': tool, 'defaultEnabled': enabled,
                                **({'defaultReason': 'Connect and confirm this project’s repository before new sessions default to Push on.'} if tool == 'studio.push_project' and not enabled else {})}
                               for tool, enabled in defaults.items()]
            from skill_application import options as skill_options
            result['skills'] = skill_options(projects)
            return result
        finally: store.close()
    store = SessionStore(projects, r4os, ident, kind)
    try:
        op = request['operation']
        if op == 'list': return store.list()
        if op == 'create': return store.create(request['input'], provider_dir)
        if op == 'get': return store.get(request['sessionId'])
        if op=='screenshots':
            from screenshot_gallery import page
            return page(store,request['sessionId'],request.get('cursor'),request.get('limit',32))
        if op=='screenshot':
            from screenshot_gallery import member
            return member(store,request['sessionId'],request['jobId'],request['evidenceId'])
        if op == 'update': return store.update(request['sessionId'], request['input'], provider_dir)
        if op == 'history':
            try:
                from image_recovery import reconcile
                reconcile(store,request['sessionId'])
            except Exception:pass  # Original unknown items/data remain; never replay effects.
            return store.history(request['sessionId'], request.get('before'), request.get('limit', 50))
        raise ProjectFault('Unsupported session operation.', 400)
    finally: store.close()


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072: raise ProjectFault('Session request too large.', 400)
    value = operation(*sys.argv[1:4], json.loads(raw))
    print(json.dumps({'result': value}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except ProjectFault as e:
        print(json.dumps({'error': str(e), 'code': e.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Session storage is unavailable.', 'code': 503})); sys.exit(1)
