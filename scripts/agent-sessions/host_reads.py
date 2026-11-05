"""Read-only coordinator projections; each invocation owns its full store life."""
from contextlib import closing
from pathlib import Path
import sqlite3
from owner import binding
from session_store import SessionStore, identity
from store import ProjectFault

OPERATIONS = frozenset(('events', 'goal', 'goal_receipt', 'goal_clock', 'run_receipt',
    'messages', 'message_receipt', 'environment_notes', 'environment_note_receipt', 'session_delete_receipt', 'statistics'))


def read(config, request):
    op = request['operation']
    if op == 'statistics':
        from stats_store import read as statistics, scope
        selection = request.get('scope', 'global')
        if selection == 'global': return statistics(config['projects'])
        kind, ident = binding(request)
        if selection == 'project':
            if kind != 'project': raise ProjectFault('Project statistics need a project owner.', 400)
            from project_use import acquire
            from store import connect
            with acquire(config['projects'], ident), closing(connect(Path(config['projects']), read_only=True)) as db:
                if not db.execute("SELECT 1 FROM projects WHERE id=? AND state='ready'", (ident,)).fetchone():
                    raise ProjectFault('Project not found.', 404)
                return statistics(config['projects'], 'project:' + scope({'type':kind,'id':ident}))
        if selection != 'session': raise ProjectFault('Invalid statistics scope.', 400)
    kind, ident = binding(request)
    sid = identity(request['sessionId'])
    store = SessionStore(config['projects'], config['r4os'], ident, kind, read_only=True)
    try:
        if op != 'session_delete_receipt': store.row(sid)
        if op == 'events':
            from run_store import events
            return events(store, sid, request.get('after', 0), details=request.get('eventPage') != 1, through=request.get('through'))
        if op in ('goal', 'goal_receipt'):
            from goal_store import Goals
            goals = Goals(store)
            return goals.snapshot(sid) if op == 'goal' else goals.receipt(sid, identity(request['requestId']))
        if op == 'goal_clock':
            from goal_clock import snapshot
            return {'clock':snapshot(store, sid)}
        if op == 'run_receipt':
            row = store.db.execute('SELECT * FROM runs WHERE session_id=? AND request_id=?', (sid,identity(request['requestId']))).fetchone()
            if not row: raise ProjectFault('Original run request not found.', 404)
            return store.run_present(row)
        if op in ('messages', 'message_receipt'):
            from message_store import Messages
            messages = Messages(store)
            return messages.snapshot(sid, request.get('before'), request.get('view','all')) if op == 'messages' else messages.receipt(sid, request['requestId'])
        if op in ('environment_notes', 'environment_note_receipt'):
            from environment_notes import Notes
            notes = Notes(store)
            return notes.listing(sid, request.get('query')) if op == 'environment_notes' else notes.deletion_receipt(sid, request['requestId'])
        if op == 'session_delete_receipt':
            # A deletion receipt does not require a surviving session row.
            from session_delete import original
            return original(store, sid, request['requestId'])
        if op == 'statistics':
            from goal_total import snapshot
            return statistics(config['projects'], 'session:' + scope({'type':kind,'id':ident},sid)) | {'totalGoalRuntime':snapshot(store,sid)}
        raise ProjectFault('Unsupported local read.', 400)
    finally:
        store.close()


def reconcile_statistics(config, cursor, session_cursors):
    # One original owner/session per bounded pass, with all lifetimes, SQLite
    # transactions and deduplicated numeric writes wholly inside this thread.
    from skill_lifecycle import api as lifecycle
    from owner import owners, skills_root
    from store import connect
    from usage_stats import Usage
    from stats_store import Source
    from stats_lifecycle import flush_pending
    with lifecycle.lock(Path(config['projects']).parent/'Skills',fault=ProjectFault):
        with closing(connect(Path(config['projects']),read_only=True)) as db:
            registered=[('project',r['id']) for r in db.execute("SELECT id FROM projects WHERE state='ready' ORDER BY id")]+owners(config['projects'])
        flush_pending(config['projects'])
        if not registered: return cursor,None,None
        kind,ident=registered[cursor%len(registered)]
        root=skills_root(config['projects']) if kind=='skill' else Path(config['projects'])
        if not (root/ident/'Sessions/Sessions.sqlite').is_file(): return cursor+1,None,None
        key=None;next_index=None;store=None
        try:
            store=SessionStore(config['projects'],config['r4os'],ident,kind)
            sessions=store.db.execute('SELECT id FROM sessions ORDER BY id').fetchall()
            if not sessions:
                Source(store).flush(include_acknowledged=True)
                return cursor+1,None,None
            key=(kind,ident);index=session_cursors.get(key,0);sid=sessions[index%len(sessions)]['id'];next_index=index+1
            store.row(sid)  # Revalidate current owner/session before any numeric write.
            Usage(store,sid).scan();Source(store).flush(include_acknowledged=True)
            return cursor+1,key,next_index
        except (ProjectFault,OSError,sqlite3.Error):
            # Failed originals stay in their outbox for the existing next pass;
            # one unavailable owner must not starve every other owner/session.
            return cursor+1,key,next_index
        finally:
            if store is not None:store.close()
