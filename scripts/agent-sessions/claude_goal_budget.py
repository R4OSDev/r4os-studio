"""Original-Play active-time authority, separate from observational GoalClock.

Only the living original worker may record qualified retry-wait intervals.
These records never admit inference, clear a quota hold, or restore a worker.
"""
import hashlib

from session_store import encode, identity
from store import ProjectFault

MAX_NS = 2**63 - 1


def invalid():
    raise ProjectFault('The original Claude Goal active-time evidence is unconfirmed. No continuation was authorized.', 409)


def number(value):
    if type(value) is not int or not 0 <= value <= MAX_NS:
        invalid()
    return value


def claim(value):
    if (not isinstance(value, dict) or set(value) != {'ordinal', 'holdId', 'stepInputId', 'failedResultId'}
            or type(value.get('ordinal')) is not int or not 1 <= value['ordinal'] <= MAX_NS):
        invalid()
    for key in ('holdId', 'stepInputId', 'failedResultId'):
        try:
            identity(value[key])
        except (ProjectFault, ValueError, TypeError):
            invalid()
    return value


def receipt(value):
    if (not isinstance(value, dict) or set(value) != {'kind', 'inputId', 'messageId'}
            or value['kind'] not in ('cancelled', 'nativeInputReceipt')):
        invalid()
    if value['kind'] == 'cancelled':
        if value['inputId'] is not None or value['messageId'] is not None:
            invalid()
    else:
        try:
            identity(value['inputId']); identity(value['messageId'])
        except (ProjectFault, ValueError, TypeError):
            invalid()
        if value['inputId'] != value['messageId']:
            invalid()
    return dict(value)


def _read(record, now):
    if not isinstance(record, dict) or 'startedNs' not in record:
        invalid()
    now = number(now); started = record.get('startedNs')
    if started is not None:
        number(started)
        if started > now:
            invalid()
    value = record.get('retryTime')
    if value is None:
        return started, None
    if (started is None or not isinstance(value, dict)
            or set(value) != {'schema', 'startedNs', 'ordinal', 'excludedNs', 'lastClosed', 'hold'}
            or type(value.get('schema')) is not int or value['schema'] != 1
            or number(value['startedNs']) != started):
        invalid()
    ordinal = number(value['ordinal']); excluded = number(value['excludedNs'])
    last = value['lastClosed']; previous_end = started
    if last is not None:
        if (not isinstance(last, dict) or set(last) != {'claim', 'startedNs', 'endedNs', 'excludedBeforeNs', 'receipt', 'sha256'}):
            invalid()
        previous = claim(last['claim']); beginning = number(last['startedNs']); ending = number(last['endedNs'])
        before = number(last['excludedBeforeNs'])
        if (not started <= beginning <= ending <= now or before > beginning - started
                or excluded != before + ending - beginning
                or previous['ordinal'] != ordinal - (value['hold'] is not None)):
            invalid()
        confirmation = receipt(last['receipt'])
        if confirmation['inputId'] == previous['stepInputId']:
            invalid()
        expected = hashlib.sha256(encode({key: field for key, field in last.items() if key != 'sha256'}).encode()).hexdigest()
        if last['sha256'] != expected:
            invalid()
        previous_end = ending
    elif excluded != 0 or ordinal != (1 if value['hold'] is not None else 0):
        invalid()
    hold = value['hold']
    if hold is not None:
        if not isinstance(hold, dict) or set(hold) != {'claim', 'startedNs'}:
            invalid()
        current = claim(hold['claim']); beginning = number(hold['startedNs'])
        if (current['ordinal'] != ordinal or not previous_end <= beginning <= now
                or last is not None and (current['holdId'] == last['claim']['holdId']
                    or current['failedResultId'] == last['claim']['failedResultId'])):
            invalid()
    if excluded > previous_end - started:
        invalid()
    return started, value


def elapsed_ns(record, now):
    """Malformed authority fails closed; legacy records retain their full time."""
    started, value = _read(record, now)
    if started is None:
        return 0
    excluded = value['excludedNs'] if value else 0
    if value and value['hold'] is not None:
        excluded += now - value['hold']['startedNs']
    if excluded > now - started:
        invalid()
    return now - started - excluded


def begin(record, original, now):
    """Record an already qualified final-failure wait, never qualify one here."""
    original = claim(original); started, value = _read(record, now)
    if started is None:
        invalid()
    if value is None:
        value = {'schema': 1, 'startedNs': started, 'ordinal': 0, 'excludedNs': 0, 'lastClosed': None, 'hold': None}
    if value['hold'] is not None:
        if value['hold']['claim'] != original:
            invalid()
        return False
    last = value['lastClosed']
    if (original['ordinal'] != value['ordinal'] + 1
            or last is not None and (original['holdId'] == last['claim']['holdId']
                or original['failedResultId'] == last['claim']['failedResultId'])):
        invalid()
    value['ordinal'] = original['ordinal']
    value['hold'] = {'claim': dict(original), 'startedNs': now}
    record['retryTime'] = value
    return True


def finish(record, original, now, confirmation=None):
    """End only the same interval after a checked input receipt or cancellation."""
    original = claim(original); _, value = _read(record, now)
    if not value:
        invalid()
    confirmation = receipt(confirmation if confirmation is not None
                           else {'kind': 'cancelled', 'inputId': None, 'messageId': None})
    if value['hold'] is None:
        if (not value['lastClosed'] or value['lastClosed']['claim'] != original
                or value['lastClosed']['receipt'] != confirmation):
            invalid()
        return False
    hold = value['hold']
    if hold['claim'] != original:
        invalid()
    closed = {'claim': dict(original), 'startedNs': hold['startedNs'], 'endedNs': now,
              'excludedBeforeNs': value['excludedNs'],
              'receipt': confirmation}
    closed['sha256'] = hashlib.sha256(encode(closed).encode()).hexdigest()
    updated = {**value, 'excludedNs': value['excludedNs'] + now - hold['startedNs'],
               'lastClosed': closed, 'hold': None}
    # Validate before a caller may commit or use the new authority value.
    _read({**record, 'retryTime': updated}, now)
    record['retryTime'] = updated
    return True
