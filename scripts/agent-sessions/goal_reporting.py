"""Authority to report status from the calling run's bound Play."""
from goal_keepalive import row as keepalive_row
from goal_store import Goals
from run_store import get_run
from session_store import encode


REASONS = {
    'no_goal': 'This session has no saved Goal.',
    'goal_inactive': 'The saved Goal is not active.',
    'goal_paused': 'The user paused this Goal.',
    'goal_stopped': 'The user stopped this Goal.',
    'goal_unconfirmed': 'The original Goal control is unconfirmed.',
    'run_without_play': 'This run has no original Goal Play binding.',
    'play_superseded': 'A newer Play or Goal generation superseded this run.',
    'other_goal_run': 'The active Goal belongs to a different run.',
    'run_ended': 'The calling run is ending or has ended.',
}


def state(worker, *, original=None, execution=None, goal_id=None):
    snapshot = Goals(worker.store).snapshot(worker.session_id)
    goal = snapshot['goal']
    if not goal:
        code = 'no_goal'
    elif snapshot['phase'] != 'idle':
        code = 'goal_unconfirmed'
    elif goal['status'] != 'active':
        code = {'pause':'goal_paused','stop':'goal_stopped'}.get(snapshot.get('lastIntent'), 'goal_inactive')
    elif 'keepalive' in snapshot:
        live = keepalive_row(worker.store, worker.session_id)
        if original is None:
            code = 'run_without_play'
        elif (not live or live.get('generation') != original['generation']
                or live.get('playRequestId') != original['playRequestId']
                or (live.get('goal') or {}).get('goalId') != original['goal']['goalId']):
            code = 'play_superseded'
        elif not live.get('active') or live.get('phase') != 'idle' or live['goal']['status'] != 'active':
            code = 'goal_inactive'
        elif live.get('runId') != worker.run_id or live.get('dispatch', {}).get('runId') != worker.run_id:
            code = 'other_goal_run'
        else:
            code = None
    elif not execution:
        code = 'run_without_play'
    elif goal.get('goalId') != goal_id or goal.get('executionId') != execution:
        code = 'play_superseded'
    elif snapshot.get('runId') != worker.run_id:
        code = 'other_goal_run'
    else:
        code = None

    if code is None:
        run = get_run(worker.store, worker.run_id)
        if getattr(worker, 'stopping', False) or not run['busy'] or run['state'] != 'running':
            code = 'run_ended'
    return {**snapshot, 'callingRunId':worker.run_id, 'canReportStatus':code is None,
            'reportStatusReasonCode':code, 'reportStatusReason':REASONS.get(code)}


def read(worker, **binding):
    return {'success':True, 'output':encode(state(worker, **binding))}


def denied(value):
    return {'success':False, 'error':'notActive', 'reasonCode':value['reportStatusReasonCode'],
            'output':encode(value)}
