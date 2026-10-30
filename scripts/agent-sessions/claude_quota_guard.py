"""Stop admitted Claude work on verified shared account holds; never resume it."""
import asyncio

from claude_quota_store import QuotaStore
from message_store import Messages,exists
from store import ProjectFault


def intent_time(worker):
    if exists(worker.store):
        row=worker.store.db.execute('SELECT created_at FROM session_messages WHERE session_id=? AND request_id=?',
            (worker.session_id,worker.row['request_id'])).fetchone()
        if row:return row[0]
    if worker.config.get('claudeGoalExecution'):
        from goal_store import Goals
        return Goals(worker.store).command(worker.session_id,worker.row['request_id'])['created_at']
    return worker.row['created_at']


def effective_hold(worker,saved):
    if not saved:return None
    if saved['hold']:return saved['hold']
    previous=saved.get('lastReleasedHold')
    if (previous and intent_time(worker)<=previous['createdAt']
        and getattr(worker,'quota_authorized_through',None)!=previous['id']):return previous
    return None


def block(worker,hold):
    w=worker
    if w.done.is_set() or w.stopping or w.quota_blocked is not None:return False
    reason=hold['reason'];w.quota_blocked=hold
    w.admission_denial={'allowed':False,'reasonCode':hold['reasonCode'],'reason':reason}
    w.error=reason;w.outcome='failed'
    if w.broker:w.broker.stop_admission()
    try:
        if exists(w.store):Messages(w.store).hold(w.session_id,reason+' Continue explicitly after a fresh limit check.')
        if w.claude_goal and w.claude_goal.started:w.claude_goal.journal.stop(reason)
    except Exception:
        w.uncertain_effect=True
        w.error='The native quota stop could not confirm its local ledger. Original effects were preserved.'
    w.defer_stop()
    return True


async def watch(worker):
    try:
        while not worker.done.is_set() and not worker.stopping:
            if worker.sent:
                saved=await asyncio.to_thread(QuotaStore(worker.manifest['providers']).read,worker.config['providerId'])
                hold=effective_hold(worker,saved)
                if hold:
                    block(worker,hold);return
            await asyncio.sleep(.5)
    except asyncio.CancelledError:pass
    except (ProjectFault,OSError,ValueError,TypeError,KeyError):
        block(worker,{'reasonCode':'proof_unavailable','reason':'The original Claude quota state is unavailable. Check this provider before continuing.'})
