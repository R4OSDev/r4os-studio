"""Explicit desktop publication, bound to one project, VM and verified deployment."""
import hashlib
import json
import re
from contracts import DevelopmentFault, UnconfirmedGuestEffect, digest, encode
from jobs import now
from layout import save
from inbox_sftp import InboxSftp
from installed_sftp import InstalledRead


def link_path(project_id):
    return '/C/R4OS/DESKTOP/S' + hashlib.sha256(project_id.encode()).hexdigest()[:7].upper() + '.LNK'


def title(project):
    text = re.sub(r'[^A-Za-z0-9 ._()\-]', ' ', project['name'])
    return ' '.join(text.split())[:64].strip() or project['moduleName']


def content(project, deployment, display_title=None):
    target = deployment['guestDirectory'] + '\\APP.R4X'
    if not re.fullmatch(r'[A-Z]:\\Build\\P[A-F0-9]{7}\\D[A-F0-9]{7}\\APP\.R4X', target):
        raise DevelopmentFault('Desktop publication requires a verified Exchange R4X deployment.')
    label = title(project) if display_title is None else display_title
    if not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9 ._()\-]{1,64}', label):
        raise DevelopmentFault('The desktop title is invalid.', 400)
    return 'R4S_FORMAT=1\nSCHEMA=R4LNK\nTARGET=' + target + '\nTITLE=' + label + '\nPOLICY=gui\nICON=INTERNAL\n'


def setup(store):
    with store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS desktop_shortcuts(vm_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')


def previous(store, vm):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='desktop_shortcuts' AND type='table'").fetchone(): return None
    row = store.db.execute('SELECT payload FROM desktop_shortcuts WHERE vm_id=?', (vm['id'],)).fetchone()
    if not row: return None
    value = json.loads(row[0])
    if value.get('state') != 'published':
        raise DevelopmentFault('The original desktop publication is unconfirmed. Reconcile its original deployment job before publishing another shortcut.')
    if (value.get('projectId') != store.id or value.get('vmId') != vm['id']
            or value.get('imageSha256') != vm['imageSha256'] or value.get('systemGeneration') != vm.get('systemGeneration')):
        raise DevelopmentFault('The desktop ownership receipt belongs to another guest identity. Existing links were preserved.')
    if store.get(value['jobId'])['state'] != 'completed':
        raise DevelopmentFault('Reconcile the original desktop deployment before replacing its shortcut.')
    return value


class DesktopRead(InstalledRead):
    """Read-only SFTP, with an exact private path set and tiny content quota."""
    def __init__(self, ssh, paths, guard=lambda: None):
        InboxSftp.__init__(self, ssh, guard)
        self.paths = {path: 4096 for path in paths}

    async def text(self, path):
        info = await self.stat(path)
        if info is None: return None
        if not info['regular'] or info['bytes'] > 4096:
            raise DevelopmentFault('The original desktop receipt is not a bounded regular file.')
        handle = await self.open(path); data = bytearray()
        while True:
            part = await self.read(handle, len(data))
            if not part: break
            data.extend(part)
            if len(data) > info['bytes']: raise DevelopmentFault('The desktop file changed during readback.')
        await self.close(handle)
        after = await self.stat(path)
        if after != info or len(data) != info['bytes']: raise DevelopmentFault('The desktop file changed during readback.')
        try: return bytes(data).decode('utf8')
        except UnicodeError: raise DevelopmentFault('The existing desktop file has unsupported content.') from None


def record_pending(store, vm, value):
    setup(store)
    with store.db:
        store.db.execute('INSERT INTO desktop_shortcuts VALUES(?,?) ON CONFLICT(vm_id) DO UPDATE SET payload=excluded.payload',
                         (vm['id'], encode(value)))


def verify_native(store, job, deployment, pending, native):
    required = {'version': 1, 'requestId': job['id'], 'projectId': store.id, 'deploymentId': deployment['id'],
        'linkPath': pending['path'], 'target': deployment['guestDirectory'] + '\\APP.R4X',
        'content': pending['content'], 'success': True, 'readbackVerified': True, 'cleanupConfirmed': True,
        'applicationStarted': False, 'atomicResult': 0}
    if any(type(native.get(k)) is not type(v) or native.get(k) != v for k, v in required.items()):
        raise UnconfirmedGuestEffect('The desktop publication has no complete matching native receipt. No write was replayed.')


def accept(store, job, deployment, pending, native):
    verify_native(store, job, deployment, pending, native)
    inventory = store.artifact_metadata(job['artifactId']).get('resourceInventory') or {}
    icon = next((entry for entry in inventory.get('entries', []) if entry['kind'] == 'icon' and entry['index'] == 0), None)
    receipt = {key: pending[key] for key in ('projectId', 'vmId', 'imageSha256', 'systemGeneration', 'path', 'content')}
    receipt.update(state='published', jobId=job['id'], deploymentId=deployment['id'], artifactId=job['artifactId'],
        sha256=hashlib.sha256(pending['content'].encode()).hexdigest(), fullReadbackVerified=True,
        iconEmbedded=inventory.get('embeddedVerified') is True and icon is not None,
        consumerVerified=False, guestVerified=False, applicationStarted=False, checkedAt=now())
    save(store.root / 'DeployWork' / job['id'] / 'desktop-receipt.json', {'receipt': receipt, 'native': native})
    record_pending(store, job['binding'], receipt)
    return receipt


async def publish(worker, ssh, lease, deployment):
    from vm_worker import guard
    from sftp import publish_file
    store, job = worker.store, worker.job
    old = previous(store, job['binding']); path = link_path(store.id)
    check = lambda: guard(store, job, lease)
    async with DesktopRead(ssh, [path, path[:-4] + '.TMP', path[:-4] + '.BAK'], check) as reader:
        existing = await reader.text(path)
        if existing is not None and (old is None or old.get('path') != path or old.get('content') != existing):
            raise DevelopmentFault('The desktop link has no matching Studio ownership receipt or was edited. It was preserved.')
        for sibling in (path[:-4] + '.TMP', path[:-4] + '.BAK'):
            if await reader.stat(sibling) is not None:
                raise DevelopmentFault('An existing desktop stage or backup needs inspection. It was preserved.')
    data = content(store.project, deployment)
    request = {'version': 1, 'requestId': job['id'], 'projectId': store.id, 'deploymentId': deployment['id'],
        'title': title(store.project), 'previous': existing}
    source = worker.work / 'DSKIN.JSN'; save(source, request)
    guest_parent = deployment['guestDirectory']
    guest = '/' + guest_parent[0] + '/' + guest_parent[3:].replace('\\', '/')
    check(); await publish_file(ssh, source, guest + '/DSKIN.JSN', digest(source))
    from vm_client import vm_call
    info = await vm_call(lease, 'info'); check()
    pending = {'state': 'pending', 'projectId': store.id, 'vmId': job['binding']['id'],
        'imageSha256': job['binding']['imageSha256'], 'systemGeneration': job['binding'].get('systemGeneration'),
        'jobId': job['id'], 'deploymentId': deployment['id'], 'path': path, 'content': data,
        'previous': existing, 'vmInvocationId': info['invocationId'], 'createdAt': now()}
    command = deployment['guestDirectory'] + '\\STHELP.R4X ' + job['id'] + ' shortcut'
    if len(command.encode()) + 15 > 127: raise DevelopmentFault('The desktop helper command exceeds the native command budget.')
    worker.phase('publishing_desktop'); check()
    save(worker.work / 'desktop-intent.json', pending)
    save(worker.work / 'desktop-previous.json', {'path': path, 'content': existing})
    record_pending(store, job['binding'], pending)
    try:
        result = await ssh.exec(command, timeout=30, complete=True, limit=4096)
        save(worker.work / 'desktop-transport.json', result)
        if result.get('transportUncertain') or result['exitCode'] != 0: raise ValueError()
        native = json.loads(result['output'])
        async with DesktopRead(ssh, [path, guest + '/DSKOUT.JSN'], check) as reader:
            saved = await reader.text(guest + '/DSKOUT.JSN')
            if saved is None or json.loads(saved) != native or await reader.text(path) != data: raise ValueError()
        return accept(store, job, deployment, pending, native)
    except BaseException as error:
        if isinstance(error, UnconfirmedGuestEffect): raise
        raise UnconfirmedGuestEffect('Desktop publication is unconfirmed. Its original intent and backup were preserved; reconcile this job, never repeat the command.') from error


async def reconcile(store, job, host):
    """Only read the original native result; never run the helper again."""
    from recovery import read, local
    work = store.root / 'DeployWork' / job['id']
    if not (work / 'desktop-intent.json').exists():
        raise DevelopmentFault('No desktop command intent was recorded. The incomplete package was preserved.')
    pending = read(work / 'desktop-intent.json'); deployment = read(work / 'deployment-pending.json')
    request = read(work / 'DSKIN.JSN')
    if (pending.get('jobId') != job['id'] or pending.get('projectId') != store.id
            or pending.get('vmId') != job['binding']['id'] or pending.get('deploymentId') != deployment['id']
            or request.get('version') != 1 or request.get('requestId') != job['id'] or request.get('projectId') != store.id
            or request.get('deploymentId') != deployment['id'] or not isinstance(request.get('title'), str)
            or request.get('previous') != pending.get('previous')
            or pending.get('path') != link_path(store.id) or pending.get('content') != content(store.project, deployment, request['title'])
            or deployment.get('artifactId') != job['artifactId'] or deployment.get('target') != job['target']):
        raise DevelopmentFault('The original desktop intent differs from this deployment. All files were preserved.')
    row = store.db.execute('SELECT payload FROM desktop_shortcuts WHERE vm_id=?', (job['binding']['id'],)).fetchone()
    if not row or json.loads(row[0]).get('jobId') != job['id']:
        raise DevelopmentFault('This original desktop operation no longer owns its publication record.')
    if (work / 'desktop-receipt.json').exists():
        original = read(work / 'desktop-receipt.json')
        verify_native(store, job, deployment, pending, original['native'])
        result = original['receipt']
        if (result.get('jobId') != job['id'] or result.get('content') != pending['content']
                or result.get('deploymentId') != deployment['id'] or result.get('sha256') != hashlib.sha256(pending['content'].encode()).hexdigest()
                or result.get('fullReadbackVerified') is not True):
            raise DevelopmentFault('The saved desktop publication receipt is incomplete.')
    else:
        if host is None: raise DevelopmentFault('The current coordinator is required for desktop receipt reads.')
        from access import Access, SshTransport, vm_config
        from lease import VmLease, inspect
        from vm_client import vm_call
        vm = vm_config(store.r4os, job['binding']['id'])
        if vm['revision'] != job['binding']['revision']:
            raise DevelopmentFault('The VM identity changed; the old desktop command was not repeated.')
        scope = {'kind': 'recovery', 'vmRevision': vm['revision'], 'imageId': vm['imageId'], 'imageSha256': vm['imageSha256']}
        with VmLease(store.projects, vm['id'], scope) as lease:
            info = await vm_call(lease, 'info')
            if info['vm']['state'] != 'running' or not pending.get('vmInvocationId') or info['invocationId'] != pending['vmInvocationId']:
                raise DevelopmentFault('The original VM process is unavailable. No VM or publication was started.')
            guest = '/' + deployment['guestDirectory'][0] + '/' + deployment['guestDirectory'][3:].replace('\\', '/')
            response_path = guest + '/DSKOUT.JSN'; path = pending['path']
            check = lambda: inspect(store.projects, lease.id, lease.token)
            async with SshTransport(Access(store.projects, store.r4os, None), vm, lease) as ssh:
                async with DesktopRead(ssh, [response_path, path, path[:-4] + '.TMP', path[:-4] + '.BAK'], check) as reader:
                    response = await reader.text(response_path)
                    if response is None: raise DevelopmentFault('The original desktop result is still unavailable. No command was repeated.')
                    native = json.loads(response)
                    verify_native(store, job, deployment, pending, native)
                    if (await reader.text(path) != pending['content'] or await reader.stat(path[:-4] + '.TMP') is not None
                            or await reader.stat(path[:-4] + '.BAK') is not None):
                        raise DevelopmentFault('The current desktop files do not match the original completed publication.')
                result = accept(store, job, deployment, pending, native)
    deployment = {**deployment, 'desktopShortcut': result}
    path = work / 'deployment.json'
    if path.exists():
        if read(path) != deployment: raise DevelopmentFault('The original deployment receipt differs; it was preserved.')
    else: save(path, deployment)
    row = store.db.execute('SELECT payload FROM deployments WHERE job_id=?', (job['id'],)).fetchone()
    if row:
        if json.loads(row[0]) != deployment: raise DevelopmentFault('The committed deployment differs from its original publication.')
    else:
        with store.db: store.db.execute('INSERT INTO deployments VALUES(?,?,?)', (deployment['id'], job['id'], encode(deployment)))
    record_pending(store, job['binding'], result)
    recovered = local(store, job)
    if recovered is None: raise DevelopmentFault('The original deployment verification is incomplete.')
    return recovered
