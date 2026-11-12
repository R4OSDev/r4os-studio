"""Image capture remains bound to a project job, image and observed VM boot."""
import asyncio
from contracts import DevelopmentFault
from lease import VmLease, inspect
from vm_client import vm_call
from evidence import lossless_webp, png, publish, preview_response
from frame_binding import window
from jobs import now
import json
import time


def bound_lease(store,job,lease):
    value=inspect(store.projects,lease.id,lease.token);scope=value.get('scope') or {};target=job['target']
    expected={'projectId':store.id,'projectRevision':job['projectRevision'],'jobId':job['id'],
        **{key:target[key] for key in ('vmRevision','imageId','imageSha256','bootId')}}
    if value.get('vmId')!=target['vmId'] or any(scope.get(key)!=item for key,item in expected.items()):
        raise DevelopmentFault('The screenshot reservation no longer matches the original job/boot binding.')


def diagnostic_target(store, job, info):
    if info['vm']['state'] != 'running': raise DevelopmentFault('The assigned VM must already be running. No VM was started.')
    from quarantine import path, admission
    file = path(store.projects, job['target']['vmId'])
    if not file.exists(): return
    if file.resolve(strict=True) != file or file.stat().st_size > 16384:
        raise DevelopmentFault('Invalid guest recovery record.', 503)
    value = json.loads(file.read_text())
    current = store.get(job['id'])
    # A live execution already owns its claim and this same reservation. A
    # terminal/foreign/unconfirmed claim is never cleared by an observation.
    own = (current['kind'] == 'execution' and current['state'] == 'running'
        and value.get('projectId') == store.id and value.get('jobId') == job['id']
        and current.get('executionId') and value.get('executionId') == current['executionId']
        and value.get('target') == current.get('target') == job['target'])
    if not own: admission(store.projects, job['target']['vmId'], 'running')


async def capture(store, job, lease=None, state=None, observer=None, control=None, consume=None, origin=None, vm_diagnostic=False, validate=None):
    target = job.get('target')
    if not target or target['vmId'] != store.project['vmId'] or job['projectRevision'] != store.project['revision']:
        raise DevelopmentFault('This job has no current project VM target. Use a current deployment or execution.')
    if lease is None:
        scope = {'kind': 'job', 'projectId': store.id, 'projectRevision': job['projectRevision'],
            'vmRevision': target['vmRevision'], 'imageId': target['imageId'], 'imageSha256': target['imageSha256'],
            'bootId': target['bootId'], 'jobId': job['id']}
        with VmLease(store.projects, target['vmId'], scope) as held:
            return await capture(store, job, held, state, observer, control, consume, origin, vm_diagnostic, validate)
    desktop = not vm_diagnostic and bool(job.get('deploymentId') and store.deployment_metadata(job['deploymentId'])['role'] == 'desktop')
    native = {}; diagnostic = False
    started_at = now(); started = time.monotonic()
    if desktop and not vm_diagnostic:
        from deskrun import frame_ready, diagnostic_window
        diagnostic = bool(state and not frame_ready(job,state) and diagnostic_window(job,state))
        if (control is None or state is None or not (frame_ready(job, state) or diagnostic)
            or any(type(state.get(k)) is not int or state[k] <= 0 for k in ('windowWidth', 'windowHeight'))):
            raise DevelopmentFault('Desktop capture needs native content readiness or a confirmed own visible, focused process/window generation with bounded geometry. The missing identity was not guessed.', reason_code='desktop_diagnostic_identity_unavailable')
        from retired_desktop import job as reject_retired
        reject_retired(job)
        launch = job.get('desktopLaunch') or {}
        if any(key not in launch for key in ('request', 'content', 'window')):
            raise DevelopmentFault('The screenshot has no original DESKRUN frame binding. No capture was published.')
        native = {'desktopRequest': launch['request'], 'desktopContent': launch['content'],
                  'desktopWindow': launch['window'], 'windowId': state['windowId']}
        if diagnostic: native.update(diagnosticOnly=True, contentUnconfirmed=True, inputReference=False, completionReference=False)
    bound_lease(store,job,lease)
    if validate: validate()
    if vm_diagnostic:
        diagnostic_target(store, job, await vm_call(lease, 'info'))
    try: captured = await vm_call(lease, 'capture_original')
    except DevelopmentFault as error:
        # A rollback may leave this worker connected to an older web bridge.
        if error.code != 400 or str(error) != 'Unsupported private VM operation.': raise
        try: captured = await vm_call(lease, 'capture_running')
        except DevelopmentFault as legacy:
            if vm_diagnostic or legacy.code != 400 or str(legacy) != 'Unsupported private VM operation.': raise
            info = await vm_call(lease, 'info')
            if info['vm']['state'] != 'running': raise DevelopmentFault('The assigned VM is not running.')
            captured = await vm_call(lease, 'capture')
    data, width, height = png(captured)
    bound_lease(store,job,lease)
    if vm_diagnostic:
        info = await vm_call(lease, 'info')
        diagnostic_target(store, job, info)
        bound_lease(store,job,lease)
        if validate: validate()
        elapsed = int((time.monotonic() - started) * 1000)
        if elapsed > 30000: raise DevelopmentFault('The VM screenshot observation exceeded 30 seconds.')
        native.update(observationMode='vm-diagnostic', diagnosticOnly=True, inputReference=False,
            completionReference=False, process=None, captureObservation={'version': 1,
                'mode': 'observed-interval', 'startedAt': started_at, 'completedAt': now(),
                'elapsedMilliseconds': elapsed, 'appReadinessConfirmed': False})
    elif desktop:
        after = await control.call('poll')
        if consume: consume(after)
        qualified = diagnostic_window(job, after) if diagnostic else frame_ready(job, after)
        if not qualified or window(after) != window(state):
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
    webp = await asyncio.to_thread(lossless_webp, data)
    bound_lease(store,job,lease)
    if validate: validate()
    value = publish(store, job, 'screenshot', data, webp=webp, width=width, height=height,
        observer=observer, captureOrigin=origin, vmId=target['vmId'], scope='assigned-vm-screen', source='qmp-png', guestRevision=(state or {}).get('guiRevision'),
        windowVisible=None if vm_diagnostic else bool((state or {}).get('windowVisible')), windowFocused=None if vm_diagnostic else bool((state or {}).get('windowFocused')), **native)
    # Publication has fsynced these exact immutable bytes and their receipt.
    return preview_response(value,webp)
