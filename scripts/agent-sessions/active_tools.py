"""Freeze the tools available at acceptance and resolve older worker contracts."""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from tool_catalog import ROOT, catalog, declarations, digest, prepared, tool_scope

RELEASES = Path('/opt/r4os-studio/releases')


def snapshot(value, exclude=(), *, root=ROOT, names=None, version=1, presentation=None):
    scope = tool_scope(value)
    if names is None:
        source = (declarations(value,root) if isinstance(value,dict) and value.get('toolCatalog')
                  else prepared(scope,root,presentation or 'legacy').values())
        tools = [item for item in source if item['name'] not in exclude]
    else:
        definitions = prepared(scope, root, presentation or 'legacy')
        tools = [definitions[name] for name in names]
    result = {'scope':scope, 'sha256':digest(tools), 'tools':[item['name'] for item in tools]}
    if version == 2:
        result['version'] = version
        if presentation is not None: result['presentation'] = presentation
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
    return {'permissions':session['permissions'].copy(),'catalog':snapshot(session,version=2,presentation=mode)}


def roadmap_presentation(config, root):
    if not any('modelSchemas' in item for item in catalog(root)[tool_scope(config)]): return None
    return 'administration' if config.get('roadmapAdministrationEnabled') else 'standard'


def remote_jobs(store,sid):
    path=store.workspace.parent/'RemoteHosts/Jobs.sqlite'
    if not path.is_file(): return False
    try:
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.1)) as db:
            return db.execute('SELECT 1 FROM jobs WHERE session_id=? LIMIT 1',(sid,)).fetchone() is not None
    except sqlite3.Error:
        return True  # The original job reader can report why storage is unavailable.


def eligible(config, *, documents=False, images=False, goal=False, remote_history=False, roadmap_admin=True):
    from profile import NOTE_TOOLS, ROADMAP_TOOLS, REMOTE_TOOLS
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
        if name == 'read_attachment': return documents and permissions.get('studio.read_file')
        if name == 'generate_image': return direct and can_generate
        if name in ('list_generated_images','import_generated_image'): return images or can_generate
        if name in ('skill_discover','skill_call','read_skill_result'): return skills
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
    if mode=='administration' and not config.get('roadmapAdministrationEnabled'): mode='standard'
    permitted=eligible(config,documents=config.get('documentContext',False),images=images,goal=goal,
                       remote_history=tool_scope(config)=='project' and not config.get('remoteHostBinding') and remote_jobs(store,sid),
                       roadmap_admin=mode!='standard')
    names=[t['name'] for t in declarations(config,root) if permitted(t['name'][7:])]
    config['toolCatalog']=snapshot(config,root=root,names=names,version=2,presentation=mode)


def instructions(config):
    return ('\n\nCURRENT STUDIO TOOLS: Use the declared tools and argument schemas for this run. '
            'Use the session permissions, workspace ownership, provider capabilities and guest/helper readiness '
            'to determine which operations are available. Use them within the user-authorized task and verify each effect from its result.')
