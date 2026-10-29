"""Image capture remains bound to a project job, image and observed VM boot."""
from contracts import DevelopmentFault
from lease import VmLease, inspect
from vm_client import vm_call
from evidence import png, publish, response
from frame_binding import window
from jobs import now
import time


async def capture(store, job, lease=None, state=None, observer=None, control=None, consume=None):
    target = job.get('target')
    if not target or target['vmId'] != store.project['vmId'] or job['projectRevision'] != store.project['revision']:
        raise DevelopmentFault('This job has no current project VM target. Use a current deployment or execution.')
    if lease is None:
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': target['vmRevision'], 'imageId': target['imageId'], 'imageSha256': target['imageSha256'],
            'bootId': target['bootId'], 'jobId': job['id']}
        with VmLease(store.projects, target['vmId'], scope) as held:
            return await capture(store, job, held, state, observer, control, consume)
    desktop = bool(job.get('deploymentId') and store.deployment_metadata(job['deploymentId'])['role'] == 'desktop')
    native = {}
    started_at = now(); started = time.monotonic()
    if desktop:
        from deskrun import frame_ready
        if (control is None or state is None or not frame_ready(job, state)
            or any(type(state.get(k)) is not int or state[k] <= 0 for k in ('windowWidth', 'windowHeight'))):
            raise DevelopmentFault('Desktop content is not confirmed for this live process and window. Capture is unavailable until the original launch is ready.')
        native = {'desktopRequest': job['desktopLaunch']['request'], 'desktopContent': job['desktopLaunch']['content'],
                  'desktopWindow': job['desktopLaunch']['window'], 'windowId': state['windowId']}
    inspect(store.projects, lease.id, lease.token)
    try: captured = await vm_call(lease, 'capture_running')
    except DevelopmentFault as error:
        # A rollback may leave this worker connected to an older web bridge.
        if error.code != 400 or str(error) != 'Unsupported private VM operation.': raise
        info = await vm_call(lease, 'info')
        if info['vm']['state'] != 'running': raise DevelopmentFault('The assigned VM is not running.')
        captured = await vm_call(lease, 'capture')
    data, width, height = png(captured)
    inspect(store.projects, lease.id, lease.token)
    if desktop:
        after = await control.call('poll')
        if consume: consume(after)
        if not frame_ready(job, after) or window(after) != window(state):
            raise DevelopmentFault('The Desktop process, window geometry or focus changed during capture. Capture the current window again.')
        elapsed = int((time.monotonic() - started) * 1000)
        if elapsed > 30000:
            raise DevelopmentFault('The screenshot observation exceeded 30 seconds. Capture the current window again.')
        native.update(windowObservation=window(after), captureObservation={
            'version': 1, 'mode': 'observed-interval', 'startedAt': started_at, 'completedAt': now(),
            'elapsedMilliseconds': elapsed, 'revisionBefore': state.get('guiRevision'),
            'revisionAfter': after.get('guiRevision'), 'contentChanged': state.get('guiRevision') != after.get('guiRevision')})
        if state.get('gestureActive') and state.get('gestureId') == after.get('gestureId'):
            native['gestureObservation'] = {'id': state['gestureId'],
                'acceptedBefore': state.get('gestureAccepted'), 'acceptedAfter': after.get('gestureAccepted'),
                'activeBefore': True, 'activeAfter': after.get('gestureActive'),
                'releaseQueuedBefore': state.get('gestureReleaseQueued'), 'releaseQueuedAfter': after.get('gestureReleaseQueued'),
                'consumptionConfirmed': False}
        native['process'] = {**(job.get('process') or {}), **{k: after[k] for k in ('instanceId', 'generation', 'windowId')}}
    value = publish(store, job, 'screenshot', data, width=width, height=height,
        observer=observer, scope='assigned-vm-screen', source='qmp-png', guestRevision=(state or {}).get('guiRevision'),
        windowVisible=bool((state or {}).get('windowVisible')), windowFocused=bool((state or {}).get('windowFocused')), **native)
    # Publication has fsynced these exact immutable bytes and their receipt.
    return response(value, data)
