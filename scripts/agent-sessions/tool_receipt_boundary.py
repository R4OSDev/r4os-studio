"""Read-only original end proofs shared by continuations and model changes."""
from goal_recovery import resolved_stop
from store import ProjectFault


def require(store, sid, message):
    for tool in store.db.execute("""SELECT t.run_id,t.call_id,t.tool,t.state,
        substr(t.result,1,262145) AS result,substr(t.intent,1,8193) AS intent
        FROM tools t JOIN runs r ON r.id=t.run_id
        WHERE r.session_id=? AND (t.state NOT IN ('completed','failed') OR t.result IS NULL)""", (sid,)):
        if not resolved_stop(store, sid, tool):
            raise ProjectFault(message, 409)
