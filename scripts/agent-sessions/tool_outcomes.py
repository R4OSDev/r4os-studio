"""Report a missing tool response as failure while retaining evidence of effects."""
import asyncio


def reported_result(result):
    if result.get('error') != 'unknown' and result.get('state') != 'unknown':
        return result
    failure = {**result, 'success': False, 'error': 'resultUnavailable', 'partialChangesPossible': True}
    if failure.get('state') == 'unknown':
        failure['state'] = 'failed'
    return failure


def terminal_result(name, result):
    if name not in ('exec_command', 'write_stdin') or not result.get('success') or result.get('state') != 'exited':
        return result
    if result.get('processEndConfirmed') is not True or type(result.get('exitCode')) is not int:
        return reported_result({**result, 'error': 'unknown'})
    if result['exitCode'] == 0 and not result.get('reason'):
        return result
    error = 'commandTimedOut' if result.get('reason') == 'timeout' else 'commandFailed'
    return {**result, 'success': False, 'error': error}


async def execute_with_deadline(worker, name, arguments, call_id, seconds):
    clock = asyncio.get_running_loop()
    deadline = clock.time() + seconds
    timer = asyncio.timeout_at(deadline)
    try:
        async with timer:
            result = await worker.execute(name, arguments, call_id)
    except TimeoutError:
        if not timer.expired():
            raise
        result = {}
    if not timer.expired() and clock.time() < deadline:
        return terminal_result(name, result)

    # Cancellation can return a final process receipt or leave a separately
    # owned development/remote job. Keep the available original evidence.
    pending = worker.items.get(call_id, {})
    evidence = {key: pending[key] for key in ('development', 'remote', 'github', 'output') if key in pending}
    if name in ('write_stdin', 'terminate_process'):
        evidence['processId'] = arguments['processId']
    failure = {**evidence, **reported_result(result), 'success': False, 'error': 'deadlineExceeded', 'deadlineSeconds': seconds}
    if not failure.get('output'):
        failure['output'] = f'The tool exceeded its Studio deadline of {seconds} seconds.'
    if not name.startswith(('read_', 'list_', 'get_')) and name not in ('search', 'skill_discover', 'validate_skill', 'web_search'):
        failure.setdefault('partialChangesPossible', True)
    return failure
