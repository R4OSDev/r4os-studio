"""One admitted interrupt inside an owned, bounded drag; no native command replay."""
import asyncio
from contracts import DevelopmentFault, UnconfirmedGuestEffect
from jobs import now
from layout import save


def validate(value, plan):
    if not isinstance(value, dict) or value.get('action') not in ('escape', 'resize', 'minimize'):
        raise DevelopmentFault('Choose Escape, resize or minimize as the drag interrupt.', 400)
    keys = {'action', 'atMilliseconds'} | ({'width', 'height'} if value['action'] == 'resize' else set())
    if set(value) != keys or type(value.get('atMilliseconds')) is not int:
        raise DevelopmentFault('Unexpected drag interrupt fields or timing.', 400)
    if len(plan) < 2 or plan[-1]['phase'] != 'up':
        raise DevelopmentFault('A drag interrupt needs a held prefix followed by its final up.', 400)
    # The fully validated gesture must be holding its final button here. No
    # further move/key input may race a changed view after the interrupt.
    if not plan[-2]['atMilliseconds'] <= value['atMilliseconds'] <= plan[-1]['atMilliseconds']:
        raise DevelopmentFault('Schedule the interrupt between the last held step and final up.', 400)
    if value['action'] != 'escape' and value['atMilliseconds'] > 1000:
        raise DevelopmentFault('Schedule a native drag window action by 1000 milliseconds.', 400)
    if value['action'] == 'resize':
        from window_control import validate as validate_window
        validate_window({k: v for k, v in value.items() if k != 'atMilliseconds'})
    return dict(value)


async def prepare(execution, message, plan, request, lease, authorization):
    from authorization import authorize
    from vm_worker import guard
    value = validate(message['input']['interrupt'], plan)
    if not authorization or authorization['engine']['profile'] not in ('studio-tools-v17','studio-tools-v18', 'studio-tools-v19', 'studio-tools-v20'):
        raise DevelopmentFault('Drag interrupts require a new v17 session; this conversation keeps its original tools.', 403)
    store = execution.store; job = store.get(execution.job['id'])
    deployment = store.deployment(job['deploymentId'])
    if deployment.get('helperCapabilities', {}).get('dragInterruptVersion') != 1:
        raise DevelopmentFault('Deploy the artifact with the new drag-interrupt-v1 helper before this check.')
    native = {'action': value['action'], 'atMilliseconds': value['atMilliseconds']}
    record = {'schema': 1, 'jobId': job['id'], 'executionId': job['executionId'],
        'requestId': message['requestId'], 'target': job['target'], 'process': job['process'],
        'input': message['input'], 'createdAt': now()}
    if value['action'] != 'escape':
        from window_control import next_operation
        guard(store, job, lease)
        authorize(store, message['owner'], 'window', message['peerPid'], job)
        if job.get('windowControlRequested') is not True or not (job.get('windowControl') or {}).get('available'):
            raise DevelopmentFault('The original run needs windowControl=true and its confirmed own-window delegation.')
        operation = next_operation(job)
        store.update(job['id'], windowOperationCounter=operation)
        prepared = await execution.control.call('window_prepare', windowOperation=operation, windowKind=value['action'],
            windowWidth=value.get('width', 0), windowHeight=value.get('height', 0))
        if not isinstance(prepared.get('nativeRequest'), str):
            raise DevelopmentFault('The original drag window action could not be prepared; no input was queued.')
        native['nativeRequest'] = prepared['nativeRequest']
        record.update(operationId=operation, nativeRequest=prepared['nativeRequest'])
    # The entire effect-bearing request, including the native token and
    # deadline, is durable before the first mouse event can be queued.
    save(execution.work / ('gesture-' + message['requestId'] + '.intent.json'), record)
    guard(store, job, lease)
    authorize(store, message['owner'], 'input', message['peerPid'], store.get(job['id']))
    if value['action'] != 'escape': authorize(store, message['owner'], 'window', message['peerPid'], store.get(job['id']))
    request.update(gestureInterruptVersion=1, gestureInterrupt=native)
    return record


async def receipt(execution, message, state, result, record, lease):
    from vm_worker import guard
    from window_control import public
    action = record['input']['interrupt']['action']
    value = {**record['input']['interrupt'], 'heldAtDispatch': state.get('gestureInterruptHeld') is True,
        'dispatchedAtMilliseconds': state.get('gestureInterruptAtMilliseconds'),
        'confirmed': state.get('gestureInterruptConfirmed') is True,
        'consumptionConfirmed': False}
    if action != 'escape' and state.get('gestureWindowSubmitted'):
        operation = record['operationId']
        native = await execution.control.call('window_status', windowOperation=operation)
        for _ in range(12):
            if 'transportError' in native or native.get('phase') not in (2, 3) or native.get('frameReady') is True: break
            await asyncio.sleep(.1); guard(execution.store, execution.store.get(execution.job['id']), lease)
            native = await execution.control.call('window_status', windowOperation=operation)
        save(execution.work / ('gesture-' + message['requestId'] + '.window.json'), {'operationId': operation, 'native': native, 'observedAt': now()})
        if 'transportError' in native or native.get('operationId') != operation or native.get('phase') in (2, 8):
            raise UnconfirmedGuestEffect('The original drag window action is unconfirmed. Read operation ' + operation + '; no gesture or command was replayed.')
        value['window'] = public(native, message['requestId'])
        # A later applied receipt cannot prove the mouse was still held at
        # apply time. Both observations are required for this interaction.
        value['confirmed'] = value['confirmed'] and value['window']['appliedConfirmed']
        execution.store.update(execution.job['id'], windowControl={'version': 1, 'available': True,
            'operationId': operation, 'native': value['window']})
    result['interrupt'] = value
    result['complete'] = result['complete'] and value['confirmed'] and value['heldAtDispatch']
    save(execution.work / ('gesture-' + message['requestId'] + '.receipt.json'), {'result': result, 'observedAt': now()})
    return result
