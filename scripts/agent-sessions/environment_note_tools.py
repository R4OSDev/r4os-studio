"""Frozen, session-bound local notes; no original-tool retries or reporting loop."""
from tool_catalog import tool_scope
import json
from store import ProjectFault

def availability(profile):
    return {'available': tool_scope(profile) in ('project', 'skill')}

def declared(worker):
    """Frozen declaration rights, independent of the first starting/running turn."""
    row=worker.store.db.execute('SELECT session_id FROM runs WHERE id=?',(worker.run_id,)).fetchone()
    return (worker.config.get('environmentNotesEnabled') is True
        and availability(tool_scope(worker.config))['available']
        and worker.config.get('owner')=={'type':worker.store.owner_type,'id':worker.store.owner_id}
        and row is not None and row['session_id']==worker.session_id)

def require(worker):
    row=worker.store.db.execute('SELECT session_id,busy,state FROM runs WHERE id=?',(worker.run_id,)).fetchone()
    if (worker.config.get('environmentNotesEnabled') is not True
            or not availability(tool_scope(worker.config))['available']):raise ProjectFault('Environment notes are unavailable or disabled for this run.',403)
    if (worker.config.get('owner')!={'type':worker.store.owner_type,'id':worker.store.owner_id}
            or not row or row['session_id']!=worker.session_id or not row['busy'] or row['state']!='running' or worker.stopping):raise ProjectFault('Environment note admission is closed for this run.',409)

def result(value):return {'success':True,'output':json.dumps(value,ensure_ascii=False,separators=(',',':'))}

def replay(worker,name,arguments,previous):
    from environment_notes import Notes,hashed
    # Recover only this local atomic receipt. Other tool Unknown handling stays
    # unchanged. Never execute the original request or return deleted note text.
    if name=='record_environment_note':
        receipt=Notes(worker.store).call_receipt(worker.session_id,previous['run_id'],previous['call_id'],hashed(arguments))
        if receipt:return result(receipt)
        if previous['result']:
            original=json.loads(previous['result'])
            if original.get('error')!='unknown' and not original.get('success'):return original
        return {'success':False,'error':'noteUnconfirmed','output':'No committed original note receipt was found. The note was not repeated. Read the current notes before considering a new relevant report.'}
    return {'success':False,'error':'readAgain','output':'Read the current notes with a new call before recording; historical note contents were not replayed.'}

def execute(worker,name,arguments,call):
    from environment_notes import Notes
    require(worker);notes=Notes(worker.store)
    try:
        value=(notes.read_tool(worker.session_id,worker.run_id,call,arguments) if name=='read_environment_notes'
               else notes.record(worker.session_id,worker.run_id,call,arguments,worker.manifest['version']))
        return result(value)
    except ProjectFault as error:return {'success':False,'error':'noteRejected','output':str(error)[:400]}

INSTRUCTIONS = '''
STUDIO ENVIRONMENT NOTES
Consider one optional note for an evidenced Studio or non-editable environment fault, or a concrete workflow improvement. Read current notes and use their revision. Leave similar or deleted reports alone. Describe the affected component, observed behavior and impact. Keep notes factual, short and free of secrets, private paths, raw logs or attachments. Use the evidence already available and continue the user's task.
'''


def instructions(config):
    return '\n\n'+INSTRUCTIONS if config.get('environmentNotesEnabled') is True and availability(tool_scope(config))['available'] else ''
