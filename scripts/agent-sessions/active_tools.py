"""Freeze the tools available at acceptance and resolve older worker contracts."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from tool_catalog import ROOT, argument_requirements, catalog, declarations, digest, execution_timeout, prepared, restricted, tool_definitions, tool_scope

RELEASES = Path('/opt/r4os-studio/releases')


def snapshot(value, exclude=(), *, root=ROOT, names=None, version=1, presentation=None, actions=None, requirements=None, file_writes=None, run_timeout=None, result_ids=None, vm_recovery=None):
    scope = tool_scope(value)
    if names is None:
        source = (declarations(value,root) if isinstance(value,dict) and value.get('toolCatalog')
                  else prepared(scope,root,presentation or 'legacy',file_writes,run_timeout,result_ids,vm_recovery).values())
        tools = [item for item in source if item['name'] not in exclude]
    else:
        definitions = prepared(scope, root, presentation or 'legacy', file_writes, run_timeout, result_ids, vm_recovery)
        tools = [restricted(definitions[name],actions[name]) if actions and name in actions else definitions[name] for name in names]
    if requirements is not None:
        tools = argument_requirements(tools,scope,root,requirements,file_writes,run_timeout,result_ids,vm_recovery)
    result = {'scope':scope, 'sha256':digest(tools), 'tools':[item['name'] for item in tools]}
    if version == 2:
        result['version'] = version
        if presentation is not None: result['presentation'] = presentation
        if actions: result['actions'] = actions
        if requirements is not None: result['argumentRequirements'] = requirements
        if file_writes is not None: result['fileWritePreconditions'] = file_writes
        if run_timeout is not None: result['runTestTimeoutSeconds'] = run_timeout
        if result_ids is not None: result['resultIds'] = result_ids
        if vm_recovery is not None: result['vmRecovery'] = vm_recovery
        if root.is_relative_to(RELEASES) and (root/'release.json').is_file():
            result['release'] = json.loads((root/'release.json').read_text())['id']
    return result


def verify(config):
    if config.get('toolCatalog') is not None: declarations(config)


def worker_release(config, current, root=RELEASES):
    from store import ProjectFault
    from studio_engine import release_for
    if config['engine'].get('kind') == 'studio':
        return release_for(config['engine'], current, root)
    saved = config.get('toolCatalog')
    if saved is None: return current
    release = saved.get('release')
    if release is not None:
        if not isinstance(release,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+[-a-zA-Z0-9.]{1,100}',release):
            raise ProjectFault('The accepted tool release identity is invalid.',409)
        candidates = (root/release,)
    else:
        # Native inputs accepted before release pins still identify the exact
        # declaration bytes. Prefer the installed release when it matches.
        candidates = (current,*sorted(root.glob('*'),reverse=True))
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            if resolved != current and resolved.parent != root: continue
            if release is not None and json.loads((resolved/'release.json').read_text())['id'] != release: continue
            declarations(config,resolved)
            return resolved
        except (OSError,ValueError,KeyError): continue
    raise ProjectFault('The original accepted tool catalog is unavailable. The input was preserved.',409)


def goal_selection(store,sid):
    session=store.get(sid)
    mode = roadmap_presentation(session, ROOT)
    run_timeout = execution_timeout() if tool_scope(session)=='project' else None
    return {'permissions':session['permissions'].copy(),'catalog':snapshot(session,version=2,presentation=mode,
            requirements=2,file_writes=1,run_timeout=run_timeout,
            result_ids=1 if session.get('engine',{}).get('kind')=='studio' else None)}


def roadmap_presentation(config, root):
    if not any(item.get('modelSchemas') or item.get('dispatch') for item in catalog(root)[tool_scope(config)]): return None
    return 'administration_edit' if config.get('roadmapAdministrationEnabled') else 'standard_edit'


def remote_jobs(store,sid):
    path=store.workspace.parent/'RemoteHosts/Jobs.sqlite'
    if not path.is_file(): return False
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
            return db.execute('SELECT 1 FROM jobs WHERE session_id=? LIMIT 1',(sid,)).fetchone() is not None
    except sqlite3.Error:
        return True  # The original job reader can report why storage is unavailable.


def update_recovery_options(store, sid, project_id):
    from project_maintenance import UPDATE_TERMINAL_PHASES, read_update_record
    from session_store import identity
    from store import ProjectFault

    options = set()
    project = store.workspace.parent
    path = project / 'Development/Development.sqlite'
    if path.is_file():
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.1)) as db:
                row = db.execute("""
                    SELECT 1 FROM jobs
                    WHERE (busy=1 OR state='unknown')
                    AND kind IN ('package','update_probe','update_transfer','update_install','update_commit','update_verify','update_recovery')
                    AND json_extract(payload,'$.sessionId')=?
                    LIMIT 1
                """, (sid,)).fetchone()
            if row:
                options.add('read_update_package')
        except sqlite3.Error:
            pass

    vm = getattr(store, 'project', {}).get('vmId')
    if not vm:
        return options
    try:
        owner_path = project.parent / '.studio/development/UpdateOwners' / (identity(vm) + '.json')
        owner = read_update_record(owner_path) if owner_path.is_file() else None
    except ProjectFault:
        return options
    if not owner or any(owner.get(key) != value for key, value in
                       (('projectId', project_id), ('sessionId', sid), ('vmId', vm))):
        return options
    phase = owner.get('phase')
    if not isinstance(phase, str) or not phase:
        return options
    if phase == 'awaiting_commit':
        options.update(('read_update_package', 'commit_update', 'abort_update', 'resume_update'))
    elif phase == 'cleanup_unconfirmed':
        options.update(('read_update_package', 'cleanup_update_transport'))
    elif phase in UPDATE_TERMINAL_PHASES:
        if phase != 'rejected' and not owner.get('cleanupConfirmed'):
            options.update(('read_update_package', 'cleanup_update_transport'))
        if phase in ('installed', 'live_installed', 'rolled_back') and not owner.get('proof'):
            options.update(('read_update_package', 'verify_update'))
    else:
        options.update(('read_update_package', 'verify_update', 'resume_update'))
        if owner.get('batchId'):
            options.add('abort_update')
    return options


def eligible(config, *, documents=False, images=False, goal=False, remote_history=False, roadmap_admin=True,
             vm=True, updates=None):
    from profile import NOTE_TOOLS, ROADMAP_TOOLS, REMOTE_TOOLS, UPDATE_TOOLS
    permissions=config['permissions']
    direct=config['engine'].get('kind')=='studio'
    can_generate=(config.get('imageGenerationEnabled') and permissions.get('studio.generate_image')
                  and config.get('imageGenerationTarget',{}).get('available')) if direct else config.get('nativeImageGeneration')
    skills=any(entry.get('mcp') for entry in config.get('skillAccess',{}).get('entries',[]))

    def permitted(name):
        if name in NOTE_TOOLS: return config.get('environmentNotesEnabled') is True
        if name in ROADMAP_TOOLS:
            return config.get('roadmapEnabled') is True and (name!='cleanup_roadmap' or roadmap_admin)
        if name == 'web_search': return direct and config.get('webSearchEnabled') is True
        if name in ('get_goal','update_goal'):
            return bool(config.get('goalKeepalive') or direct and (goal or config.get('goalExecution') or config.get('studioGoalPreparation')))
        if not permissions.get('studio.'+name): return False
        if updates is not None and name in UPDATE_TOOLS:
            return name in updates and (vm or name in ('read_update_package', 'plan_update_package', 'build_update_package'))
        if name == 'read_attachment': return documents and permissions.get('studio.read_file')
        if name == 'generate_image': return direct and can_generate
        if name in ('list_generated_images','import_generated_image'): return images or can_generate
        if name in ('skill_discover','skill_call','read_skill_result'): return skills
        if name in ('start_project_vm','stop_project_vm','restart_project_vm','run_vm_command','capture_vm',
                    'send_vm_input','control_app_window','deploy_project','run_project') and not vm: return False
        if name=='restart_project_vm': return permissions.get('studio.start_project_vm') and permissions.get('studio.stop_project_vm')
        if name=='complete_development_job': return permissions.get('studio.run_project') and permissions.get('studio.stop_development_job')
        if name=='control_app_window': return permissions.get('studio.run_project')
        if name in REMOTE_TOOLS:
            return bool(config.get('remoteHostBinding') or (remote_history and name in ('read_remote_job','stop_remote_job')))
        if name == 'push_project': return bool(config.get('githubBinding'))
        if name == 'read_context_result': return direct
        return True

    return permitted


def freeze(store,sid,config,*,images):
    from goal_store import exists as goals_exist
    saved=config.get('toolCatalog')
    root=ROOT
    if saved:
        root=worker_release({**config,'engine':{'kind':'native'}},ROOT)
        if root!=ROOT and config['engine'].get('kind')=='studio':
            from studio_engine import engine
            config['engine']=engine(tool_scope(config),config['engine'].get('api'),root=root)
        if saved.get('version',1)==1: return
    goal=goals_exist(store) and store.db.execute('SELECT 1 FROM session_goals WHERE session_id=? AND native IS NOT NULL',(sid,)).fetchone() is not None
    if not goal and config.get('goalKeepaliveControl'):
        from goal_keepalive import row
        goal=bool((row(store,sid) or {}).get('goal'))
    mode = saved.get('presentation') if saved else roadmap_presentation(config,root)
    if mode in ('administration', 'administration_edit') and not config.get('roadmapAdministrationEnabled'):
        mode=roadmap_presentation(config,root)
    file_writes = saved.get('fileWritePreconditions') if saved else 1
    scope = tool_scope(config)
    run_timeout = saved.get('runTestTimeoutSeconds') if saved else execution_timeout(root) if scope=='project' else None
    result_ids = saved.get('resultIds') if saved else 1 if config['engine'].get('kind')=='studio' else None
    vm_recovery = saved.get('vmRecovery') if saved else 1 if scope=='project' else None
    definitions=tool_definitions(scope,root,file_writes,run_timeout,result_ids,vm_recovery)
    updates = None
    if 'check_update' in definitions:
        from profile import UPDATE_TOOLS
        updates = (UPDATE_TOOLS if config.get('updateToolsEnabled') is True
                   else update_recovery_options(store, sid, config['owner']['id']))
    permitted=eligible(config,documents=config.get('documentContext',False),images=images,goal=goal,
                       remote_history=tool_scope(config)=='project' and not config.get('remoteHostBinding') and remote_jobs(store,sid),
                       roadmap_admin=mode not in ('standard', 'standard_initialize', 'standard_edit'),vm=bool(getattr(store,'project',{'vmId':True}).get('vmId')) if tool_scope(config)=='project' else False,
                       updates=updates)
    names=[];actions={}
    for tool in declarations(config,root):
        full=tool['name']; name=full[7:]
        dispatch=definitions[name].get('dispatch')
        if dispatch:
            original=(saved or {}).get('actions',{}).get(full,dispatch)
            available=[action for action in original if permitted(dispatch[action]['tool'])]
            if available:
                names.append(full);actions[full]=available
        elif permitted(name): names.append(full)
    requirements = saved.get('argumentRequirements') if saved else 2
    config['toolCatalog']=snapshot(config,root=root,names=names,version=2,presentation=mode,actions=actions,
                                  requirements=requirements,file_writes=file_writes,run_timeout=run_timeout,result_ids=result_ids,
                                  vm_recovery=vm_recovery)


def instructions(config):
    return ('\n\nCURRENT STUDIO TOOLS: Use the declared tools and argument schemas for this run. '
            'Use the session permissions, workspace ownership, provider capabilities and guest/helper readiness '
            'to determine which operations are available. Use them within the user-authorized task and verify each effect from its result.')
