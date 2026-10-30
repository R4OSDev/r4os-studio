"""Observed window identity is separate from its continuously changing content."""
import datetime

WINDOW_FIELDS = ('instanceId', 'generation', 'windowId', 'windowWidth', 'windowHeight', 'windowVisible', 'windowFocused')


def window(state):
    return {key: state.get(key) for key in WINDOW_FIELDS}


def current(image, job, state, maximum_age=30, focused=False):
    """Validate a recent observed interval, never claim an atomic guest frame."""
    process = job.get('process') or {}
    observed = image.get('process') or {}
    if (image.get('diagnosticOnly') or image.get('contentUnconfirmed') or image.get('kind') != 'screenshot' or not image.get('bootId')
        or image['bootId'] != (job.get('target') or {}).get('bootId')
        or not process.get('instanceId') or state.get('state') != 'running'
        or state.get('closeConfirmed') or state.get('stopReason') or not state.get('windowVisible')
        or any(observed.get(k) != process.get(k) or state.get(k) != process.get(k) for k in ('instanceId', 'generation'))
        or observed.get('windowId') != state.get('windowId') or (focused and not state.get('windowFocused'))):
        return False
    interval = image.get('captureObservation')
    try:
        stamp = interval['completedAt'] if isinstance(interval, dict) else image['createdAt']
        elapsed = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(stamp)).total_seconds()
        if not 0 <= elapsed <= maximum_age: return False
    except (KeyError, TypeError, ValueError): return False
    if interval is None:
        # Historical images have no geometry observation. Keep their original
        # strict content check rather than inventing new evidence for them.
        return image.get('guestRevision') == state.get('guiRevision')
    return (isinstance(interval, dict) and interval.get('version') == 1 and interval.get('mode') == 'observed-interval'
        and image.get('windowObservation') == window(state))
