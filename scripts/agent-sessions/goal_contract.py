"""Qualified native Goal projection; no local execution state or model calls."""
import json
from pathlib import Path

STATUSES = ('active', 'paused', 'blocked', 'usageLimited', 'budgetLimited', 'complete')
MAX_OBJECTIVE_CHARS = 4000
MAX_SAFE_INTEGER = 9007199254740991
# Rust str::trim uses Unicode White_Space, unlike Python's additional C0 chars.
WHITESPACE = ''.join(chr(c) for c in [*range(9, 14), 32, 133, 160, 5760,
                                    *range(8192, 8203), 8232, 8233, 8239, 8287, 12288])


def objective(value, allow_empty=False):
    if not isinstance(value, str): raise ValueError('Enter a Goal as text.')
    if any(0xD800 <= ord(c) <= 0xDFFF or c == '\x00' for c in value):
        raise ValueError('The Goal contains invalid Unicode text.')
    value = value.strip(WHITESPACE)
    if len(value) > MAX_OBJECTIVE_CHARS: raise ValueError('A Goal may contain at most 4000 Unicode characters.')
    if not value and not allow_empty: raise ValueError('Enter a Goal.')
    return value


def native_goal(value, thread_id):
    if value is None: return None
    if not isinstance(value, dict) or value.get('threadId') != thread_id or value.get('status') not in STATUSES:
        raise ValueError('The native Goal belongs to another thread or has an unsupported status.')
    result = {'threadId': thread_id, 'objective': objective(value.get('objective')), 'status': value['status']}
    for key in ('tokensUsed', 'timeUsedSeconds', 'createdAt', 'updatedAt'):
        number = value.get(key)
        if type(number) is not int or not 0 <= number <= MAX_SAFE_INTEGER:
            raise ValueError('The native Goal contains invalid usage or time values.')
        result[key] = number
    budget = value.get('tokenBudget')
    if budget is not None and (type(budget) is not int or not 1 <= budget <= MAX_SAFE_INTEGER):
        raise ValueError('The native Goal contains an invalid reported budget.')
    if 'tokenBudget' in value: result['tokenBudget'] = budget
    return result


def save_params(thread_id, text, previous=None):
    """Omit unchanged objective and any budget; preserve native usage/accounting."""
    text = objective(text, allow_empty=True)
    if not text: return 'thread/goal/clear', {'threadId': thread_id, 'origin': 'user'}
    params = {'threadId': thread_id, 'origin': 'user', 'status': 'paused'}
    if previous is None or previous['objective'] != text: params['objective'] = text
    return 'thread/goal/set', params


def capability():
    contract = json.loads((Path(__file__).resolve().parents[2] / 'shared/agent-input-capabilities.json').read_text())
    return {'contractQualified': True, 'nativeVersion': contract['qualifiedRuntime']['version'],
            'maxObjectiveChars': MAX_OBJECTIVE_CHARS, 'statuses': list(STATUSES),
            'budgetControls': False, 'requiresGoalWorker': True}
