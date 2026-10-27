"""Safe catalog metadata for settings and frozen runs; never connects to SSH."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
from profile import REMOTE_PROFILE


def context(store, fresh=False):
    if not fresh and hasattr(store, '_remote_host_context'): return store._remote_host_context
    from remote_binding import get
    with closing(sqlite3.connect((store.projects / 'Projects.sqlite').as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
        host_id = get(db, store.project_id)
    host = None; reason = 'No Remote Host is assigned to this project.'
    if host_id:
        helper = Path(__file__).resolve().parents[1] / 'remote-hosts/metadata.py'
        try:
            result = subprocess.run(['/usr/bin/python3', '-B', str(helper), str(store.projects.parent / 'RemoteHosts'), host_id],
                capture_output=True, timeout=5,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
            if len(result.stdout) > 32768: raise ValueError()
            value = json.loads(result.stdout)
            if result.returncode or value.get('error'): raise ValueError()
            host = value['result']
            if host.get('id') != host_id or 'password' in host: raise ValueError()
            reason = 'The assigned host is available for explicit remote work. Use Check connection before commands or files; historical checks do not prove current reachability.'
        except (OSError, ValueError, subprocess.TimeoutExpired):
            reason = 'The assigned Remote Host metadata is unavailable. Restore its catalog before remote work; the VM remains independent.'
    value = (host, {'available': host is not None, 'assignedId': host_id, 'reason': reason})
    store._remote_host_context = value
    return value


def availability(store, profile):
    if profile != REMOTE_PROFILE:
        return {'available': False, 'reason': 'New session required for Remote Host tools. This conversation keeps its original native profile and history.'}
    host, value = context(store)
    return {**value, **({'hostName': host['name']} if host else {})}


def freeze(store, profile, enabled):
    if profile != REMOTE_PROFILE or not enabled: return None, {'available': False, 'reason': 'This run has no compatible Remote Host tool binding.'}
    return context(store, fresh=True)


def snapshot(store, profile, enabled):
    host, access = context(store, fresh=True)
    compatible = profile == REMOTE_PROFILE and enabled
    return {'remoteHostContext': host, 'remoteHostBinding': host if compatible else None,
            'remoteHostAccess': access if compatible else {**access, 'available': False, 'reason': 'New session or compatible coordinator required for Remote Host tools; this run keeps its original profile.'}}
