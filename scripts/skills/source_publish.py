"""Publish a complete source package; preserve local drafts and original bindings."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

STARTER = b'---\nname: new-skill\ndescription: ""\n---\n\n'


def prepare_package(api, root, ident, job, source, manifest, progress):
    config = job['configuration']
    runtime = None
    package = source / 'Repository'
    if config['skillPath']:
        package = package / config['skillPath']
    if config['recipe'] is not None:
        try:
            from rea_recipe import prepare as prepare_rea
        except ImportError:
            raise api.SkillFault('The managed REA runtime recipe is not available in this installed release yet.', 409) from None
        package, runtime = prepare_rea(api, root, ident, job, source, manifest, progress)
    else:
        prefix = config['skillPath'] + '/' if config['skillPath'] else ''
        for entry in manifest['files']:
            if entry['path'].startswith(prefix) and (entry.get('inertLink') or entry.get('lfs')):
                raise api.SkillFault('The selected skill requires a linked or unresolved LFS resource. Its actual content must be prepared before activation.', 409)
    package = api.folder(package)
    if not package.is_relative_to(source / 'Repository') and not package.is_relative_to(root / ident / 'Runtimes'):
        raise api.SkillFault('The prepared skill package is outside its managed source/runtime.', 503)
    files, contents, tree_hash = api.inventory(package)
    validation = api.validate(files, contents, tree_hash, '/usr/bin/node')
    if not validation['valid']:
        raise api.SkillFault('The repository skill is invalid: ' + '; '.join(validation['errors']), 409)
    return files, contents, tree_hash, runtime


def publish(api, db, root, ident, job, source, manifest, manifest_hash, progress):
    files, contents, incoming_hash, runtime = prepare_package(api, root, ident, job, source, manifest, progress)
    binding = dict(schema=1, repository=job['configuration']['repository'], commit=manifest['commit'],
                   sourceManifestHash=manifest_hash, skillPath=job['configuration']['skillPath'],
                   recipe=job['configuration']['recipe'], importedHash=incoming_hash, runtime=runtime)
    api.source_binding.validate(binding, api.SkillFault)
    activations = api.folder(root / ident / 'Activations', True)
    operation = api.folder(activations / job['requestId'], True)
    candidate = api.folder(operation / 'Incoming', True)
    if any(candidate.iterdir()):
        raise api.SkillFault('The original activation has existing staging. Reconcile it before another publication.', 409)
    for file in files:
        path = candidate / file['path']
        api.folder(path.parent, True)
        api.atomic(path, contents[file['path']], file['executable'])
    api.sync(candidate)
    progress(phase='publishing')
    with api.locked(root, ident):
        current = api.detail(db, root, ident)
        meta = api.sources.read(db, ident)
        if (not meta or meta['revision'] != job['sourceRevision'] or meta.get('lastRequestId') != job['requestId']
                or current['skill']['revision'] != job['skillRevision'] or current['draftHash'] != job['draftHash']):
            raise api.SkillFault('The skill or source changed during preparation. Its current draft and active revision were preserved.', 409)
        actual_files, actual, _ = api.inventory(root / ident / 'Workspace')
        untouched_starter = len(actual_files) == 1 and actual.get('SKILL.md') == STARTER
        upstream_hash = (meta.get('active') or {}).get('importedHash')
        if (upstream_hash is not None and current['draftHash'] != upstream_hash
                or upstream_hash is None and not untouched_starter and current['draftHash'] != incoming_hash):
            raise api.SkillFault('This draft contains local changes. Preserve or reconcile them before replacing it from GitHub.', 409)
        original = root / ident / 'Workspace'
        backup = operation / 'Previous'
        journal = dict(schema=1, requestId=job['requestId'], skillId=ident, phase='prepared',
                       previousDraftHash=current['draftHash'], incomingHash=incoming_hash,
                       previousActiveHash=current['skill']['activeHash'], sourceBinding=binding)

        def stage(phase):
            journal['phase'] = phase
            api.atomic(operation / 'journal.json', (api.encode(journal) + '\n').encode())

        stage('swap_intent')
        os.rename(original, backup)
        api.sync(original.parent)
        try:
            os.rename(candidate, original)
            api.sync(original.parent)
            stage('swapped')

            class Owner:
                def verify(self, actual_root, actual_id):
                    if actual_root != root or actual_id != ident:
                        raise api.SkillFault('The source publication owner changed.', 403)

            payload = dict(id=ident, revision=current['skill']['revision'], draftHash=incoming_hash,
                           requestId=str(uuid.uuid5(uuid.UUID(job['requestId']), 'publish-source-package')))
            result = api.publish(db, root, payload, '/usr/bin/node', author=Owner(), publication=binding)
            if not result.get('saved'):
                raise api.SkillFault('The complete source skill could not be published.', 503)
            journal.update(packageHash=result['skill']['activeHash'], activeRevision=result['skill']['activeRevision'])
            stage('published')
        except BaseException:
            if db.in_transaction:
                db.rollback()
            # Only restore this operation's known draft while its author lock is held.
            active = db.execute('SELECT active_hash FROM skills WHERE id=?', (ident,)).fetchone()[0]
            if active == current['skill']['activeHash']:
                if original.exists() and api.inventory(original)[2] == incoming_hash:
                    os.rename(original, operation / 'Rejected')
                if not original.exists() and backup.is_dir() and api.inventory(backup)[2] == current['draftHash']:
                    os.rename(backup, original)
                    api.sync(original.parent)
                    stage('rolled_back')
            raise
        if backup.exists():
            shutil.rmtree(backup)
        stage('complete')
    return dict(published=True, packageHash=result['skill']['activeHash'], activeRevision=result['skill']['activeRevision'],
                importedHash=incoming_hash, runtime=runtime)
