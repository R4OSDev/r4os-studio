"""Only Studio's published immutable skill resources enter a run's catalogue."""
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import stat
from owner import skills_root
from store import ProjectFault

spec = importlib.util.spec_from_file_location('skill_resource_store', Path(__file__).resolve().parents[1] / 'skills/store.py')
packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)
MAX_ACTIVE = 64
MAX_CATALOG = 96 * 1024
MAX_RESOURCES = 128 * 1024 * 1024


def catalog(projects):
    path = skills_root(projects) / 'Skills.sqlite'
    if not path.exists() and not path.is_symlink(): return []
    try:
        if path.resolve(strict=True) != path or not stat.S_ISREG(path.stat().st_mode): raise ValueError()
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            if db.execute('PRAGMA user_version').fetchone()[0] != 1: raise ValueError()
            db.execute('BEGIN')
            rows = db.execute("SELECT * FROM skills WHERE state='ready' ORDER BY created_at,id LIMIT 257").fetchall()
            sources = {row['id']: packages.sources.read(db, row['id']) for row in rows}
        if len(rows) > 256: raise ValueError()
        result = []
        for row in rows:
            from skill_lifecycle import api
            if api.deleted(skills_root(projects),row['id']):continue
            value = packages.summary(row); packages.identity(value['id'])
            source = sources[value['id']]
            if source and source.get('active') and source['active'].get('packageHash') == value['activeHash']:
                value['sourceAttached'] = True
            if not isinstance(value['name'], str) or not 1 <= len(value['name']) <= 120: raise ValueError()
            if not isinstance(value['description'], str) or len(value['description']) > 1024: raise ValueError()
            if type(value['revision']) is not int or value['revision'] < 1: raise ValueError()
            if type(value['activeRevision']) is not int or value['activeRevision'] < 0: raise ValueError()
            if value['activeRevision'] == 0 and value['activeHash'] is not None: raise ValueError()
            result.append(value)
        return result
    except (OSError, ValueError, sqlite3.Error, packages.SkillFault):
        raise ProjectFault('The global skill catalog is unavailable. Existing data was preserved.', 503) from None


class Snapshot:
    """One operation's catalogue and verified metadata; never a process-wide cache."""
    def __init__(self, projects):
        self.projects = projects; self.entries = catalog(projects)
        self.members = {entry['id'] for entry in self.entries}; self.revisions = {}

    def revision(self, entry, verify_files=False):
        key = packages.encode([entry.get(name) for name in ('id','activeHash','formatName','description','manifestHash')])
        previous = self.revisions.get(key)
        if previous and (previous[1] or not verify_files):
            from skill_lifecycle import api
            if api.deleted(skills_root(self.projects),entry['id']):
                raise ProjectFault('The published skill was retired during preparation.',409)
            return previous[0]
        result = revision(self.projects, entry, verify_files, _members=self.members)
        self.revisions[key] = result, verify_files
        return result


def revision(projects, entry, verify_files=False, *, _members=None):
    try:
        ident = packages.identity(entry['id'])
        from skill_lifecycle import api
        members = _members if _members is not None else {v['id'] for v in catalog(projects)}
        if api.deleted(skills_root(projects),ident) or ident not in members:raise ValueError()
        tree_hash = entry['activeHash']
        if not isinstance(tree_hash, str) or not re.fullmatch('[a-f0-9]{64}', tree_hash): raise ValueError()
        root = skills_root(projects) / ident / 'Revisions' / tree_hash
        raw, _ = packages.regular(packages.folder(root) / 'revision.json')
        if len(raw) > 131072: raise ValueError()
        data = json.loads(raw); files = data['files']; metadata = data['metadata']
        binding = data.get('sourceBinding') if data.get('schema') == 2 else None
        expected_fields = ({'schema', 'files', 'hash', 'metadata', 'draftHash', 'sourceBinding'} if binding is not None
                           else {'files', 'hash', 'metadata'})
        if (data['hash'] != tree_hash or not isinstance(files, list) or not 1 <= len(files) <= 128
                or set(data) != expected_fields
                or metadata != {'name': entry['formatName'], 'description': entry['description']}
                or packages.source_binding.package_hash(packages, files, binding) != tree_hash): raise ValueError()
        files_hash = packages.digest(packages.encode(files).encode())
        if binding is not None and data['draftHash'] != files_hash: raise ValueError()
        total = 0; paths = set()
        for file in files:
            if set(file) != {'path', 'sha256', 'bytes', 'executable'}: raise ValueError()
            packages.relative(file['path'])
            if (file['path'] in paths or type(file['bytes']) is not int or not 0 <= file['bytes'] <= 1048576
                    or type(file['executable']) is not bool or not re.fullmatch('[a-f0-9]{64}', file['sha256'])): raise ValueError()
            paths.add(file['path']); total += file['bytes']
        if 'SKILL.md' not in paths or total > 8 * 1048576: raise ValueError()
        manifest_hash = hashlib.sha256(raw).hexdigest()
        if 'manifestHash' in entry and entry['manifestHash'] != manifest_hash: raise ValueError()
        workspace = packages.folder(root / 'Workspace')
        if verify_files:
            actual, _, actual_hash = packages.inventory(workspace)
            if actual != files or actual_hash != files_hash: raise ValueError()
        return workspace, files, manifest_hash, total
    except (OSError, ValueError, KeyError, TypeError, packages.SkillFault):
        raise ProjectFault('The published revision for skill ' + str(entry.get('name', entry.get('id', 'unknown'))) +
                           ' is unavailable or changed. Review it in Skill Manager before running.', 409) from None


def options(projects):
    snapshot = Snapshot(projects)
    result = []
    for entry in snapshot.entries:
        available, reason = entry['activeRevision'] > 0, 'No published revision. Save a valid skill to make it available.'
        if available:
            try: snapshot.revision(entry)
            except ProjectFault: available = False; reason = 'The published revision is unavailable. Review it in Skill Manager.'
        result.append({'id': entry['id'], 'name': entry['name'], 'description': entry['description'],
                       'available': available, **({} if available else {'reason': reason})})
    return result


def freeze(store, choices, terminal=False, mcp=False):
    snapshot = Snapshot(store.projects)
    enabled = [entry for entry in snapshot.entries if choices.get(entry['id'], True)]
    entries, unavailable = [], []; total = 0
    for entry in enabled:
        if not entry['activeRevision']:
            unavailable.append({'id': entry['id'], 'name': entry['name'], 'reason': 'No published revision.'}); continue
        if len(entries) >= MAX_ACTIVE: raise ProjectFault('More than 64 global skills are enabled. Disable some in Session settings before sending.', 409)
        workspace, files, manifest_hash, size = snapshot.revision(entry, verify_files=True)
        total += size
        if total > MAX_RESOURCES: raise ProjectFault('Enabled global skills exceed 128 MiB of resources. Disable some in Session settings.', 409)
        frozen = {key: entry[key] for key in ('id', 'name', 'revision', 'formatName', 'description', 'activeRevision', 'activeHash')}
        frozen.update(manifestHash=manifest_hash, files=files)
        if mcp and entry.get('sourceAttached'):
            raw, _ = packages.regular(workspace.parent / 'revision.json')
            source = json.loads(raw).get('sourceBinding')
            if source and source.get('runtime') is not None:
                from skill_runtime import freeze as freeze_runtime
                frozen['mcp'] = freeze_runtime(store.projects, entry['id'], source)
        entries.append(frozen)
    alias = None
    for number in range(16):
        candidate = '__studio_skills__' + (str(number + 1) if number else '')
        target = store.workspace / candidate
        if not target.exists() and not target.is_symlink(): alias = candidate; break
    if alias is None and entries: raise ProjectFault('The virtual skill paths conflict with workspace entries. Review the reserved namespace before running.', 409)
    value = {'schema': 1, 'alias': alias, 'entries': entries, 'unavailable': unavailable, 'terminal': terminal}
    if len(catalog_text(value).encode()) > MAX_CATALOG: raise ProjectFault('The enabled global skill catalog exceeds 96 KiB. Disable some skills in Session settings.', 409)
    return value


def catalog_text(value, paths=None, config=None):
    if value.get('schema') != 1:
        raise ProjectFault('Unsupported frozen skill access version.', 409)
    if not value['entries']:
        return ''
    resource_paths = (paths or {}).get('skills', {})
    rows = [
        {'id': entry['id'], 'name': entry['name'], 'description': entry['description'],
         'activeRevision': entry['activeRevision'],
         'readPath': resource_paths.get(entry['id'], value['alias'] + '/' + entry['id']) + '/SKILL.md',
         **({'terminalPath': resource_paths.get(entry['id'], '/skills/' + entry['id'])} if value.get('terminal') else {}),
         **({'mcp': True} if entry.get('mcp') else {})}
        for entry in value['entries']
    ]
    guidance = ('Use a matching skill and read its SKILL.md via root=workspace and readPath. '
                'Resolve references relative to that file. Follow the user task and current tool permissions.')
    if value.get('terminal'):
        guidance += ' Use terminalPath for the published scripts and keep task outputs in the workspace.'
    if any(row.get('mcp') for row in rows):
        from tool_catalog import result_readback
        read=result_readback(config or {},'skill')
        guidance += ' Use studio_skill_discover for exact native names and schemas.'
        if read:
            reader=read['tool']+(' with action=skill' if read.get('action') else '')
            guidance += ' Follow result cursors with '+reader+'.'
        guidance += ' Use the schema and exact argumentsJson in studio_skill_call.'
        if (config or {}).get('reaPaths') == 1:
            guidance += (' For local REA file arguments, use project-relative paths or the /workspace/ prefix. '
                         'Studio resolves /session/... to private analysis files and accepts returned attachment paths.')
    return ('\n\nCURRENT STUDIO GLOBAL SKILLS\n' + guidance + '\n'
            + json.dumps(rows, ensure_ascii=True, separators=(',', ':')))
