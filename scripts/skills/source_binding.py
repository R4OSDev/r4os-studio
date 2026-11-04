"""Immutable source/runtime provenance participates in a published package identity."""
import re


def validate(binding, fault):
    if binding is None:
        return
    fields = {'schema', 'repository', 'commit', 'sourceManifestHash', 'skillPath', 'recipe', 'importedHash', 'runtime'}
    if not isinstance(binding, dict) or set(binding) != fields or binding.get('schema') != 1:
        raise fault('Invalid published source binding.', 503)
    if (not isinstance(binding['repository'], str) or not re.fullmatch(
            'https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', binding['repository'])
            or not re.fullmatch('[a-f0-9]{40}', binding['commit'] or '')
            or any(not isinstance(binding[k], str) or not re.fullmatch('[a-f0-9]{64}', binding[k])
                   for k in ('sourceManifestHash', 'importedHash'))
            or not isinstance(binding['skillPath'], str) or len(binding['skillPath']) > 240
            or binding['recipe'] not in (None, 'rea')):
        raise fault('Invalid published source identity.', 503)
    runtime = binding['runtime']
    if runtime is not None:
        if (not isinstance(runtime, dict) or set(runtime) != {'path', 'manifestHash', 'version'}
                or not isinstance(runtime['path'], str) or not re.fullmatch(
                    'Runtimes/' + binding['commit'] + '/[a-f0-9]{64}', runtime['path'])
                or not isinstance(runtime['manifestHash'], str) or not re.fullmatch('[a-f0-9]{64}', runtime['manifestHash'])
                or not isinstance(runtime['version'], str) or not 1 <= len(runtime['version']) <= 80):
            raise fault('Invalid published runtime identity.', 503)
    if (binding['recipe'] is None) != (runtime is None):
        raise fault('The published skill and runtime do not match.', 503)


def package_hash(api, files, binding):
    validate(binding, api.SkillFault)
    return api.digest(api.encode(files if binding is None else {'schema': 2, 'files': files, 'sourceBinding': binding}).encode())


def current(api, db, root, ident, active_hash):
    source = api.sources.read(db, ident)
    if not source or not source.get('active') or source['active'].get('packageHash') != active_hash:
        return None
    raw, _ = api.regular(root / ident / 'Revisions' / active_hash / 'revision.json')
    binding = __import__('json').loads(raw).get('sourceBinding')
    validate(binding, api.SkillFault)
    return binding


def attach(api, db, ident, package_hash_value, draft_hash, binding):
    source = api.sources.read(db, ident)
    if source is None or binding is None:
        return
    active = dict(repository=binding['repository'], commit=binding['commit'], packageHash=package_hash_value,
                  draftHash=draft_hash, importedHash=binding['importedHash'], runtime=binding['runtime'])
    source.update(active=active, updatedAt=api.now())
    # A normal local Save may occur during an explicit source download. Preserve
    # that job's progress; only the publishing worker decides its final phase.
    db.execute('UPDATE skill_sources SET metadata=? WHERE skill_id=?', (api.encode(source), ident))
