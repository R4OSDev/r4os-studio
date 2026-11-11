"""Report a missing tool response as failure while retaining evidence of effects."""


def reported_result(result):
    if result.get('error') != 'unknown' and result.get('state') != 'unknown':
        return result
    failure = {**result, 'success': False, 'error': 'resultUnavailable', 'partialChangesPossible': True}
    if failure.get('state') == 'unknown':
        failure['state'] = 'failed'
    return failure
