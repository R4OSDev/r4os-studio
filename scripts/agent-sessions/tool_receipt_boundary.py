"""Read-only original end proofs shared by continuations and model changes."""
import hashlib

from goal_recovery import resolved_stop
from session_store import encode
from store import ProjectFault


def fingerprint(tool,arguments):
    return hashlib.sha256(encode({'tool':tool,'arguments':arguments}).encode()).hexdigest()


def original_hash(store,row):
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tool_call_inputs'").fetchone():
        original=store.db.execute('SELECT arguments_hash FROM tool_call_inputs WHERE run_id=? AND call_id=?',
                                  (row['run_id'],row['call_id'])).fetchone()
        if original: return original['arguments_hash']
    return row['arguments_hash']


def record_input(store,run,call,tool,arguments_hash):
    """Save the model call identity in the same transaction as its routed effect."""
    store.db.execute('''CREATE TABLE IF NOT EXISTS tool_call_inputs(
        run_id TEXT NOT NULL, call_id TEXT NOT NULL, tool TEXT NOT NULL, arguments_hash TEXT NOT NULL,
        PRIMARY KEY(run_id,call_id), FOREIGN KEY(run_id,call_id) REFERENCES tools(run_id,call_id))''')
    store.db.execute('INSERT INTO tool_call_inputs VALUES (?,?,?,?)',(run,call,tool,arguments_hash))


def require(store, sid, message):
    for tool in store.db.execute("""SELECT t.run_id,t.call_id,t.tool,t.state,
        substr(t.result,1,262145) AS result,substr(t.intent,1,8193) AS intent
        FROM tools t JOIN runs r ON r.id=t.run_id
        WHERE r.session_id=? AND (t.state NOT IN ('completed','failed') OR t.result IS NULL)""", (sid,)):
        if not resolved_stop(store, sid, tool):
            raise ProjectFault(message, 409)
