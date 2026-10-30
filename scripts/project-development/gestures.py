"""Validate the entire bounded client gesture before any event is queued."""
import asyncio
from contracts import DevelopmentFault, UnconfirmedGuestEffect


def steps(value, width, height):
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise DevelopmentFault('A gesture requires 1 to 32 steps.', 400)
    result = []; previous = -1; held = None
    for step in value:
        if not isinstance(step, dict) or step.get('phase') not in ('down', 'move', 'up'):
            raise DevelopmentFault('Use down, move or up gesture phases.', 400)
        phase = step['phase']
        required = {'phase', 'x', 'y', 'atMilliseconds'} | ({'button'} if phase != 'move' else set())
        if set(step) != required or any(type(step[key]) is not int for key in ('x', 'y', 'atMilliseconds')):
            raise DevelopmentFault('Unexpected gesture fields or non-integer coordinates/timing.', 400)
        if not 0 <= step['x'] < width or not 0 <= step['y'] < height:
            raise DevelopmentFault('Keep gesture coordinates inside the observed client area.', 400)
        timing = step['atMilliseconds']
        if not 0 <= timing <= 2000 or timing < previous:
            raise DevelopmentFault('Gesture times must be monotonic and at most 2000 milliseconds.', 400)
        previous = timing
        button = step.get('button')
        if phase != 'move' and button not in ('left', 'right'):
            raise DevelopmentFault('Choose the left or right mouse button.', 400)
        if phase == 'down':
            if held is not None: raise DevelopmentFault('Release the current gesture button before pressing another.', 400)
            held = button
        elif phase == 'up':
            if held != button: raise DevelopmentFault('A gesture can release only its own pressed button.', 400)
            held = None
        result.append({**step, **({'button': 'none'} if phase == 'move' else {})})
    if held is not None: raise DevelopmentFault('Every gesture must release its button within the same call.', 400)
    return result


async def execute(execution, message, request, state, control, lease, process, authorization):
    """One admitted gesture, observed by polling its ID; never resubmit its plan."""
    from vm_worker import guard
    from observation import capture
    from authorization import authorize
    store = execution.store; job = store.get(execution.job['id']); value = message['input']
    if authorization and authorization['engine']['profile'] != 'studio-tools-v14':
        raise DevelopmentFault('This conversation retains its original input schema. A new gesture-capable session is required.')
    deployment = store.deployment(job['deploymentId'])
    if deployment.get('helperCapabilities', {}).get('gestureVersion') != 1 or request.get('frameBindingVersion') != 1:
        raise DevelopmentFault('Deploy again with a gesture-v1 helper and capture its focused window before using gestures.')
    plan = steps(value['steps'], state['windowWidth'], state['windowHeight'])
    observe_after = value.get('observeAfterStep')
    if observe_after is not None:
        if type(observe_after) is not int or not 1 <= observe_after <= len(plan):
            raise DevelopmentFault('observeAfterStep must identify a step in this gesture.', 400)
        if authorization:
            authorize(store, message['owner'], 'capture', message['peerPid'], job)
    gesture_id = message['requestId']
    request.update(gestureVersion=1, gestureId=gesture_id, steps=plan)
    guard(store, job, lease)
    if authorization: authorize(store, message['owner'], 'input', message['peerPid'], job)
    state = await control.call('input', **request)  # Exactly once; lost ack stays unknown.
    deadline = asyncio.get_running_loop().time() + 3
    image_id = None; observation_error = None; attempted = False
    while True:
        execution.output(state); state['outputBase64'] = ''; execution.last = state
        if state.get('gestureId') != gesture_id:
            raise UnconfirmedGuestEffect('The gesture receipt has a different identity. Its plan was not replayed.')
        if not state.get('gestureActive'): break
        cancel = execution.stop_requested or store.get(job['id'])['state'] == 'stopping'
        try:
            guard(store, job, lease)
            if authorization: authorize(store, message['owner'], 'input', message['peerPid'], job)
        except DevelopmentFault: cancel = True
        if cancel:
            state = await control.call('cancel_gesture', generation=process['generation'], gestureId=gesture_id)
            continue
        if observe_after and not attempted and state.get('gestureAccepted', 0) >= observe_after:
            attempted = True
            try:
                if authorization: authorize(store, message['owner'], 'capture', message['peerPid'], job)
                image = await capture(store, job, lease, state,
                    observer={**message['owner'], 'model': authorization['model']} if authorization else None,
                    control=control, consume=execution.output,
                    origin={'requestId':message['requestId'],'operation':'input'} if authorization else None)
                image_id = image['metadata']['id']
            except DevelopmentFault as error:
                if getattr(error, 'uncertain', False): raise
                observation_error = str(error)
        if asyncio.get_running_loop().time() > deadline:
            raise UnconfirmedGuestEffect('The original gesture did not confirm its bounded end. Read the saved job; do not repeat it.')
        await asyncio.sleep(.05)
        state = await control.call('poll')
    if state.get('gestureReleaseQueued') is not True:
        raise UnconfirmedGuestEffect('The gesture ended without a confirmed release enqueue. No gesture was repeated.')
    accepted = state.get('gestureAccepted', 0)
    result = {'version': 1, 'kind': 'gesture', 'gestureId': gesture_id, 'process': process,
        'delivery': 'owned-event-queue', 'consumptionConfirmed': False,
        'accepted': accepted, 'expected': len(plan),
        'complete': accepted == len(plan) and not state.get('gestureAborted'),
        'queuedAtMilliseconds': state.get('gestureTimesMilliseconds', []),
        'releaseQueued': True, 'abortedReason': state.get('gestureAborted'),
        **({'observationId': image_id} if image_id else {}),
        **({'observationError': observation_error} if observation_error else {})}
    if observe_after and not attempted: result['observationError'] = 'The gesture ended before the requested intermediate observation was available.'
    return state, result
