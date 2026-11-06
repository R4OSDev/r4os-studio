"""Read declared tool metadata only. Never prepare, probe or execute a runtime."""
import ast
from collections import OrderedDict
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import stat
import threading

from owner import skills_root
from store import ProjectFault
from tool_catalog import catalog, native_capabilities

ROOT = Path(__file__).resolve().parents[2]
_CACHE = OrderedDict()
_LOCK = threading.Lock()
_SPEC = importlib.util.spec_from_file_location('catalog_runtime_metadata', ROOT / 'scripts/skills/runtime_spec.py')
runtime_spec = importlib.util.module_from_spec(_SPEC); _SPEC.loader.exec_module(runtime_spec)
MAX_CACHE = 32 * 1024 * 1024
PAGE = 60


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value): return hashlib.sha256(encoded(value)).hexdigest()


def facts(path, limit):
    if path.resolve(strict=True) != path: raise ValueError()
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit: raise ValueError()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def metadata(path, limit=131072):
    # The existing narrow reader checks every path component and O_NOFOLLOW.
    return runtime_spec.read(path, limit)


def declaration(raw):
    if (not isinstance(raw, dict) or not isinstance(raw.get('name'), str) or not 1 <= len(raw['name']) <= 512
            or not isinstance(raw.get('inputSchema'), dict)
            or raw.get('description') is not None and not isinstance(raw['description'], str)):
        raise ValueError()
    return {key: raw[key] for key in ('name', 'title', 'description', 'inputSchema', 'outputSchema') if key in raw}


def studio():
    merged = OrderedDict()
    for scope, tools in catalog().items():
        for raw in tools:
            value = declaration(raw); key = digest(value)
            if key not in merged: merged[key] = {**value, 'id': key, 'scopes': []}
            merged[key]['scopes'].append(scope)
    return list(merged.values())


def native():
    # Read the already declared bridge contract as a literal, without importing
    # its runtime/GOAL implementation or selecting a productive session.
    tree = ast.parse(metadata(ROOT / 'scripts/agent-sessions/claude_goal.py', 262144))
    raw = next(ast.literal_eval(n.value) for n in tree.body
               if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REPORT_TOOL' for t in n.targets))
    value = declaration(raw)
    return [{**value, 'id': digest(value), 'scopes': ['project', 'skill'],
             'context': 'Claude native bridge; only an originally accepted legacy bounded Studio GOAL. '
                        'New Goal keepalive runs use the central get_goal/update_goal contracts.'}]


def skill_sources(projects, release):
    from skill_application import packages
    from skill_lifecycle import api
    root = skills_root(projects); path = root / 'Skills.sqlite'
    if not path.exists() and not path.is_symlink(): return []
    try:
        facts(path, 64 * 1024 * 1024)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise ValueError()
            db.execute('BEGIN')
            rows = db.execute("SELECT * FROM skills WHERE state='ready' ORDER BY created_at,id LIMIT 257").fetchall()
            if len(rows) > 256: raise ValueError()
            has_sources = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_sources'").fetchone()
            sources = dict(db.execute('SELECT skill_id,CASE WHEN length(metadata)<=131072 THEN metadata ELSE NULL END FROM skill_sources WHERE skill_id IN (' + ','.join('?' for _ in rows) + ')', [r['id'] for r in rows])) if has_sources and rows else {}
        result = []
        for row in rows:
            ident = packages.identity(row['id'])
            if api.deleted(root, ident): continue
            entry = packages.summary(row)
            if not isinstance(entry['name'], str) or not 1 <= len(entry['name']) <= 120: raise ValueError()
            public = {'id': 'skill-' + ident, 'name': entry['name'], 'kind': 'mcp', 'scopes': ['project', 'skill'],
                      'identity': digest([release, ident, entry['activeRevision'], entry['activeHash'], entry['revision']]),
                      'status': 'notPrepared', 'count': None, 'reason': 'No current prepared MCP catalog. No runtime was started.'}
            private = None
            try:
                if entry['activeRevision'] < 1: raise ValueError()
                active_hash = entry['activeHash']
                if not isinstance(active_hash, str) or not re.fullmatch('[a-f0-9]{64}', active_hash): raise ValueError()
                source = json.loads(sources.get(ident) or 'null')
                if source is None:
                    result.append((public, None)); continue
                active = source.get('active')
                if not isinstance(active, dict) or active.get('packageHash') != active_hash: raise ValueError()
                revision_path = root / ident / 'Revisions' / active_hash / 'revision.json'
                revision = json.loads(metadata(revision_path))
                binding = revision.get('sourceBinding')
                packages.source_binding.validate(binding, packages.SkillFault)
                if (binding is None or revision.get('schema') != 2 or revision.get('hash') != active_hash
                        or revision.get('metadata') != {'name':entry['formatName'], 'description':entry['description']}
                        or packages.source_binding.package_hash(packages, revision['files'], binding) != active_hash
                        or any(active.get(key) != binding[key] for key in ('repository', 'commit', 'runtime'))): raise ValueError()
                runtime = binding['runtime']
                if runtime is None:
                    result.append((public, None)); continue
                runtime_root = root / ident / runtime['path']
                raw = metadata(runtime_root / 'runtime.json')
                if hashlib.sha256(raw).hexdigest() != runtime['manifestHash']: raise ValueError()
                manifest = json.loads(raw)
                if (manifest.get('schema') != 1 or manifest.get('recipe') != 'rea' or manifest.get('version') != runtime['version']
                        or manifest.get('source') != dict(repository=binding['repository'], commit=binding['commit'], manifestHash=binding['sourceManifestHash'])
                        or not isinstance(manifest.get('files'), list) or not isinstance(manifest.get('programs'), dict)):
                    raise ValueError()
                for key in ('node', 'entry'):
                    part = manifest[key]; runtime_spec.relative(part['path'])
                    if not re.fullmatch('[a-f0-9]{64}', part['sha256']): raise ValueError()
                if manifest['entry'].get('arguments') != ['mcp']:
                    raise ValueError()
                component = manifest['catalog']; runtime_spec.relative(component['path'])
                if not re.fullmatch('[a-f0-9]{64}', component['sha256']): raise ValueError()
                catalog_path = runtime_root / component['path']
                file_facts = facts(catalog_path, runtime_spec.MAX_MANIFEST)
                identity = digest([release, ident, entry['activeRevision'], active_hash, runtime['manifestHash'], component['sha256']])
                public.update(identity=identity, status='prepared', reason='Prepared metadata only; executable programs and current session permissions are not checked.',
                              revision=entry['activeRevision'], sourceCommit=binding['commit'], runtimeVersion=runtime['version'])
                private = (catalog_path, file_facts, component['sha256'], runtime['version'])
            except (OSError, ValueError, KeyError, TypeError, packages.SkillFault):
                public.update(status='unknown', reason='The current source, revision or prepared catalog is missing, changed or invalid. No older catalog was substituted.')
            result.append((public, private))
        return result
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, packages.SkillFault):
        return [({'id':'skills', 'identity':digest([release,'skills-unavailable']), 'name':'Skills', 'kind':'mcp',
                  'scopes':['project','skill'], 'status':'unknown', 'count':None,
                  'reason':'The registered skill catalog is unavailable. No runtime was started.'}, None)]


def sources(projects):
    release = json.loads(metadata(ROOT / 'shared/version.json'))['version']
    tools = studio(); native_tools = native()
    result = [({'id':'studio', 'name':'Studio', 'kind':'studio', 'identity':digest([release,tools]),
                'scopes':['project','skill'], 'status':'ready', 'count':len(tools)}, tools),
              ({'id':'native', 'name':'Native runtime functions', 'kind':'native', 'identity':digest([release,native_tools,native_capabilities()]),
                'scopes':['project','skill'], 'status':'partial', 'count':len(native_tools),
                'reason':'Only locally declared callable contracts are listed. Native built-in tool names, descriptions and schemas are not provided by the installed metadata; coverage is incomplete.',
                'capabilities':[dict(value, callable=False, schemaProvided=False) for value in native_capabilities()]}, native_tools)]
    result.extend(skill_sources(projects, release))
    return release, result


def managed(private):
    path, before, expected, version = private
    key = (str(path), before, expected, version)
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key); return cached[0]
    from skill_application import packages
    raw = metadata(path, runtime_spec.MAX_MANIFEST)
    if facts(path, runtime_spec.MAX_MANIFEST) != before or hashlib.sha256(raw).hexdigest() != expected: raise ValueError()
    value = json.loads(raw)
    if (value.get('version') != 1 or value.get('info', {}).get('version') != version
            or not isinstance(value.get('tools'), list) or not 1 <= len(value['tools']) <= 10000): raise ValueError()
    tools = []
    names = set()
    for tool in value['tools']:
        tool = declaration(tool)
        if tool['name'] in names: raise ValueError()
        names.add(tool['name']); tools.append({**tool,'id':digest(tool),'scopes':['project','skill']})
    size = len(raw)
    with _LOCK:
        _CACHE[key] = (tools, size)
        while len(_CACHE) > 8 or sum(v[1] for v in _CACHE.values()) > MAX_CACHE: _CACHE.popitem(last=False)
    return tools


def read(projects, request):
    release, entries = sources(projects)
    source_id = request.get('sourceId')
    if source_id is None:
        return {'release':release, 'revision':digest([s for s,_ in entries]), 'sources':[s for s,_ in entries],
                'coverage':'partial', 'reason':'Registration does not grant session permissions. Native coverage and unprepared sources are explicitly incomplete.'}
    source, private = next(((s,p) for s,p in entries if s['id'] == source_id), (None,None))
    if source is None: raise ProjectFault('The catalog source is no longer registered.', 404)
    if request.get('identity') != source['identity']: raise ProjectFault('The catalog source changed. Reload Tools before continuing.', 409)
    if private is None:
        if request.get('toolId') is not None: raise ProjectFault('The current tool metadata is unavailable. Reload Tools.', 409)
        return {'source':source, 'tools':[], 'next':None, 'complete':False}
    try: tools = managed(private) if source['kind'] == 'mcp' else private
    except (OSError, ValueError, KeyError, TypeError):
        if request.get('toolId') is not None: raise ProjectFault('The current tool metadata is unavailable. Reload Tools.', 409)
        return {'source':{**source,'status':'unknown','count':None,'reason':'The prepared catalog is missing, changed or invalid. No older catalog was substituted.'}, 'tools':[], 'next':None, 'complete':False}
    source = {**source, 'count':len(tools)}
    if source['status'] == 'prepared': source['status'] = 'ready'
    tool_id = request.get('toolId')
    if tool_id is not None:
        tool = next((t for t in tools if t['id'] == tool_id), None)
        if tool is None: raise ProjectFault('The tool contract is no longer available in this source.', 404)
        if len(encoded(tool)) > 1024 * 1024: raise ProjectFault('This declared contract exceeds the bounded detail size. Its complete metadata is unavailable here.', 413)
        return {'source':source, 'tool':{**tool,'description':tool.get('description'),
                'context':tool.get('context', 'Requires the selected runtime/model and the accepted session tool and skill permissions. Registration alone is not authorization.')}}
    offset = request.get('after', '0')
    if not isinstance(offset, str) or not re.fullmatch('0|[1-9][0-9]{0,5}', offset): raise ProjectFault('Invalid catalog continuation.', 400)
    offset = int(offset)
    if offset > len(tools): raise ProjectFault('The catalog continuation is no longer available.', 409)
    page = [{key:t[key] for key in ('id','name','title','scopes') if key in t} for t in tools[offset:offset+PAGE]]
    next_page = str(offset+len(page)) if offset+len(page) < len(tools) else None
    return {'source':source, 'tools':page, 'next':next_page, 'complete':next_page is None}
