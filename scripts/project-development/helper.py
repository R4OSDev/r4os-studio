"""Build private guest adapters with the accepted project's SDK authority."""
import asyncio
import json
import fcntl
import hashlib
from pathlib import Path
import uuid

from contracts import APP, DevelopmentFault, digest, encode, hash_value
from jobs import Jobs, folder, now
from snapshot import capture
from builder import Builder
from store import connect


def source_manifest(manifest, template):
    # The SDK's app entry alias follows its own generation. Use the same
    # platform query in the helper's extra desktop import.
    imports = template['imports']
    if len(imports) != 1 or imports[0] not in ('R4SYS:Query:1', 'R4SYS:Query2:2'):
        raise DevelopmentFault('The pinned SDK declares an unsupported guest helper platform import.')
    system = imports[0]
    desktop = 'R4DESK:' + system.split(':', 1)[1]
    manifest = manifest.replace(b'IMPORT=R4SYS:Query:1', b'IMPORT=' + system.encode())
    manifest = manifest.replace(b'IMPORT=R4DESK:Query:1', b'IMPORT=' + desktop.encode())
    profile = template.get('build_profile')
    if profile:
        manifest = manifest.replace(b'LANGUAGE=Zig', b'LANGUAGE=Zig\nSDK_PROFILE=' + profile.encode(), 1)
    return manifest


async def prepare_helper(projects, r4os, project_pins):
    from sdk import TYPES, profile
    from sdk_profiles import manifest_profile
    from toolset import combination
    selected = {name: project_pins[name] for name in ('sdk', 'contract', 'libraries', 'zig') if name in project_pins}
    try:
        context = await asyncio.to_thread(profile, r4os, projects, resolve_rust=False, selected=selected)
        terminal = next(value for value in TYPES if value[0] == 'terminal')
        choice = combination(context, terminal, 'Zig')
        if not choice or not choice['supported']:
            raise DevelopmentFault('The pinned SDK has no supported Zig console application template.')
        template = choice['template']
        pins = context['pins']
        pins['sdkProfile']['id'] = manifest_profile(context,
            {'language': 'Zig', 'sdk_profile': template.get('build_profile')})
        client = await prepare_one(projects, r4os, template, False, pins)
        client['watchdog'] = await prepare_one(projects, r4os, template, True, pins)
    except ValueError as error:
        detail = str(error).strip()[-1000:]
        raise DevelopmentFault('Studio guest helper preparation failed for the pinned SDK. ' + detail) from error
    return client


async def prepare_one(projects, r4os, template, watcher, pins):
    source = APP / 'guest/development-helper'
    content = {str(p.relative_to(source)): p.read_bytes() for p in sorted(source.rglob('*'))
               if p.is_file() and not p.is_symlink()}
    content['module.R4MF'] = source_manifest(content['module.R4MF'], template)
    if watcher:
        content['module.R4MF'] = content['module.R4MF'].replace(b'NAME=STHELP', b'NAME=STWATCH').replace(b'APP_CLASS=console', b'APP_CLASS=service')
        content['src/main.zig'] = b'const r4os=@import("r4os"); pub fn r4_app_main(app:*r4os.App)i32{return @import("bootstrap.zig").run(app);}'
    files = [{'path': path, 'sha256': hashlib.sha256(data).hexdigest()} for path, data in sorted(content.items())]
    key = hash_value({'source': files, 'pins': pins, 'protocol': 1})
    root = folder(Path(projects) / '.studio/development/Helpers' / key)
    with (root / 'build.lock').open('a') as lock:
        while True:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); break
            except BlockingIOError: await asyncio.sleep(.2)
        return await build_locked(root, content, files, pins, key, r4os, watcher)


async def build_locked(root, content, files, pins, key, r4os, watcher):
    project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'r4os-studio-helper:' + key))
    project = root / project_id
    if not project.exists():
        folder(project)
        for path, data in content.items():
            target = project / 'Workspace' / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    actual = [{'path': str(p.relative_to(project / 'Workspace')), 'sha256': digest(p)}
              for p in sorted((project / 'Workspace').rglob('*')) if p.is_file() and not p.is_symlink()]
    if actual != files or any(p.is_symlink() for p in (project / 'Workspace').rglob('*')):
        raise DevelopmentFault('The private helper source cache differs from this Studio release.')
    db = connect(root)
    try:
        with db:
            db.execute('INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (project_id, 'Studio guest helper', '', 'Zig', 'service' if watcher else 'terminal', 'STWATCH' if watcher else 'STHELP', None,
                 encode(pins), now(), now(), 1, 'ready'))
    finally: db.close()
    store = Jobs(root, r4os, project_id)
    try:
        for row in store.db.execute('SELECT id,payload FROM artifacts ORDER BY rowid DESC'):
            try:
                artifact = store.artifact(row['id'])
                from scratch import retire
                try: retire(store, store.get(artifact['buildId']), verified_artifact=artifact)
                except (DevelopmentFault, OSError): pass
                return {'protocol': 1, 'sourceSha256': hash_value(files), 'sha256': artifact['files'][0]['sha256'],
                        'path': store.root / 'Artifacts' / artifact['id'] / artifact['entry'],
                        'bytes': artifact['files'][0]['bytes'], 'pins': pins, 'artifact': artifact}
            except DevelopmentFault: continue
        # An interrupted helper build is never automatically resumed. A new
        # invocation can compile the same immutable helper inputs afresh.
        for row in store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchall():
            store.update(row['id'], 'unknown', error='The previous helper build ended without a receipt.')
        job, _ = store.admit('build', {'requestId': str(uuid.uuid4()), 'projectRevision': 1, 'settingsRevision': 1})
        snapshot, directory = capture(store, job); store.update(job['id'], 'running', source=snapshot, phase='compiling')
        builder = Builder(store, job)
        try: result = await asyncio.wait_for(builder.build(directory), 600)
        except DevelopmentFault as error:
            store.update(job['id'], 'failed', error=str(error))
            raise DevelopmentFault(f'The pinned Studio guest helper {store.project["moduleName"]} could not be built. '
                                   f'Build {job["id"]} failed. {error}') from error
        except BaseException:
            store.update(job['id'], 'failed', error='The pinned Studio guest helper could not be built.'); raise
        artifact = store.artifact(result['artifactId'])
        from scratch import retire
        try: retire(store, store.get(job['id']), verified_artifact=artifact)
        except (DevelopmentFault, OSError): pass
        return {'protocol': 1, 'sourceSha256': hash_value(files), 'sha256': artifact['files'][0]['sha256'],
                'path': store.root / 'Artifacts' / artifact['id'] / artifact['entry'],
                'bytes': artifact['files'][0]['bytes'], 'pins': pins, 'artifact': artifact}
    finally: store.close()
