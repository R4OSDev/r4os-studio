"""Image capture remains bound to a project job, image and observed VM boot."""
from contracts import DevelopmentFault
from lease import VmLease, inspect
from vm_client import vm_call
from evidence import png, publish, read


async def capture(store, job, lease=None, state=None, observer=None):
    target = job.get('target')
    if not target or target['vmId'] != store.project['vmId'] or job['projectRevision'] != store.project['revision']:
        raise DevelopmentFault('This job has no current project VM target. Use a current deployment or execution.')
    if lease is None:
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': target['vmRevision'], 'imageId': target['imageId'], 'imageSha256': target['imageSha256'],
            'bootId': target['bootId'], 'jobId': job['id']}
        with VmLease(store.projects, target['vmId'], scope) as held:
            return await capture(store, job, held, state, observer)
    inspect(store.projects, lease.id, lease.token)
    info = await vm_call(lease, 'info')
    if info['vm']['state'] != 'running': raise DevelopmentFault('The assigned VM is not running.')
    data, width, height = png(await vm_call(lease, 'capture'))
    inspect(store.projects, lease.id, lease.token)
    value = publish(store, job, 'screenshot', data, width=width, height=height,
        observer=observer, scope='assigned-vm-screen', source='qmp-png', guestRevision=(state or {}).get('guiRevision'),
        windowVisible=bool((state or {}).get('windowVisible')), windowFocused=bool((state or {}).get('windowFocused')))
    return read(store, job['id'], value['id'])
