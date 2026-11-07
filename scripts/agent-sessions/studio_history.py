"""Bind historical observations to their verified original receipts and end proofs."""
import hashlib
import json
import sqlite3

from goal_recovery import development, resolved_stop
from session_store import encode


def recoveries(store, sid, messages):
    result = {}
    for message in messages:
        if message.get('role') != 'tool' or type(message.get('sequence')) is not int:
            continue
        for part in message['content']:
            if part['type'] != 'tool_result' or not (part['result'].get('error') == 'unknown' or part['result'].get('partialChangesPossible')):
                continue
            try:
                bound = 'studio-' + hashlib.sha256(encode([message['runId'], part['callId']]).encode()).hexdigest()
                if (message.get('origin', {}).get('toolReceiptId') != bound
                        or part['result'].get('studioReceiptId') != bound):
                    continue
                row = store.db.execute("""SELECT t.run_id,t.call_id,t.tool,t.state,
                    t.arguments_hash,substr(t.result,1,262145) AS result,substr(t.intent,1,131073) AS intent,
                    r.state AS run_state,r.busy AS run_busy,substr(r.worker,1,32769) AS worker,
                    substr(c.content,1,1048577) AS content,substr(c.origin,1,8193) AS origin
                    FROM tools t JOIN runs r ON r.id=t.run_id
                    JOIN conversation_records c ON c.run_id=r.id AND c.session_id=r.session_id
                    WHERE r.session_id=? AND t.run_id=? AND t.call_id=? AND c.seq=?
                    AND c.record_id=? AND c.kind='message' AND c.role='tool'""",
                    (sid, message['runId'], bound, message['sequence'], message['id'])).fetchone()
                if (not row or not row['result'] or len(row['result'].encode()) > 262144
                        or len(row['content'].encode()) > 1048576 or len(row['origin'].encode()) > 8192
                        or json.loads(row['origin']).get('toolReceiptId') != bound
                        or encode(part) not in [encode(p) for p in json.loads(row['content'])]
                        or encode(part['result']) != encode({**json.loads(row['result']), 'studioReceiptId': bound})):
                    continue
                from patch_observations import confirmed
                observation=confirmed(row)
                if observation:
                    result[(message['runId'], part['callId'])]={**observation,
                        'sessionId':sid,'runId':message['runId'],'recordId':message['id'],
                        'sequence':message['sequence']}
                    continue
                if not resolved_stop(store, sid, row):continue
                value = development(store, sid, row)
                if value and value.get('stopAction') and (value.get('recovery') or {}).get('guestEndConfirmed') is True:
                    result[(message['runId'], part['callId'])] = {k: value[k] for k in
                        ('jobId', 'kind', 'state', 'stopAction', 'effectConfirmed', 'recovery')}
            except (sqlite3.Error, ValueError, KeyError, TypeError, AttributeError):
                continue  # The ordinary portability guard retains the unconfirmed observation.
    return result
