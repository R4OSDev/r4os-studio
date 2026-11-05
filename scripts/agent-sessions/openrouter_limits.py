"""Current API-key budgets in reported USD, distinct from account funding."""
import datetime
import math


def number(value, signed=False):
    return value if type(value) in (int, float) and abs(value) <= 9007199254740991 and math.isfinite(value) and (signed or value >= 0) else None


def reset(value):
    if not isinstance(value, str) or len(value) > 64:return None
    try:
        date = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.isoformat() if date.tzinfo is not None else None
    except ValueError:return None


def budget(value):
    if not isinstance(value, dict):return None
    scope = value.get('scope')
    if not isinstance(scope, str) or not 1 <= len(scope) <= 80 or any(ord(c) < 32 or ord(c) == 127 for c in scope):return None
    interval = value.get('reset_interval')
    return {'scope': scope, 'limitUsd': number(value.get('limit_usd')), 'spendUsd': number(value.get('spend_usd')),
            'remainingUsd': number(value.get('remaining_usd'), signed=True),
            'unlimited': 'limit_usd' in value and value['limit_usd'] is None,
            'resetInterval': interval if interval in ('daily', 'weekly', 'monthly') else None,
            'resetsAt': reset(value.get('resets_at')),
            'includeByok': value.get('include_byok') if type(value.get('include_byok')) is bool else None}


def normalize(body):
    data = body.get('data')
    if not isinstance(data, dict):raise ValueError()
    key = budget({'scope': 'key_limit', **({'limit_usd': data['limit']} if 'limit' in data else {}),
                  'spend_usd': data.get('usage'), 'remaining_usd': data.get('limit_remaining'),
                  'reset_interval': data.get('limit_reset'), 'include_byok': data.get('include_byok_in_limit')})
    values = data.get('budgets', [])
    if not isinstance(values, list) or len(values) > 64:raise ValueError()
    budgets = [result for value in values if (result := budget(value)) is not None]
    effective = budget(data.get('effective_budget'))
    # A reported but unreadable effective budget cannot be replaced by a
    # less restrictive legacy key cap. Keep the original response privately.
    selected = effective if data.get('effective_budget') is not None else key
    if selected and selected['scope'] == 'key_limit':
        for value in budgets:
            if value['scope'] == 'key_limit' and value['limitUsd'] == selected['limitUsd'] and value['remainingUsd'] == selected['remainingUsd']:
                selected = value;break
    remaining = None
    if selected and not selected['unlimited']:
        maximum, left = selected['limitUsd'], selected['remainingUsd']
        if maximum is not None and left is not None:
            if maximum > 0:remaining = min(100, max(0, left/maximum*100))
            elif left <= 0:remaining = 0
    usage = {field: number(data.get('usage_'+field)) for field in ('daily', 'weekly', 'monthly')}
    requests = data.get('free_model_daily_requests'); daily = None
    if isinstance(requests, dict):daily = {field: number(requests.get(field)) for field in ('used', 'limit', 'remaining')}
    return {'remainingPercent': remaining, 'openrouter': {'currency': 'USD', 'keyBudget': key,
        'effectiveBudget': effective, 'selectedBudget': selected, 'budgets': budgets, 'usage': usage,
        'freeModelDailyRequests': daily, 'source': 'https://openrouter.ai/api/v1/key'}}
