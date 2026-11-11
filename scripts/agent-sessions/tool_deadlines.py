"""Studio tool deadlines, saved globally and frozen at direct run admission."""
from contextlib import closing
import os
import sqlite3

from store import ProjectFault
from system_prompt import location
from tool_catalog import catalog


MIN_SECONDS = 1
MAX_SECONDS = 7200
DEFAULT_SECONDS = 300
LONGER = {
    'studio.build_project': 1200,
    'studio.deploy_project': 900,
    'studio.run_project': 900,
    'studio.exec_command': 600,
    'studio.start_project_vm': 600,
    'studio.stop_project_vm': 1500,
    'studio.restart_project_vm': 1500,
    'studio.run_remote_command': 600,
    'studio.remote_files': 600,
    'studio.push_project': 900,
    'studio.generate_image': 1200,
    'studio.skill_call': 900,
    'studio.build_update_package': 1200,
    'studio.upload_update_package': 1800,
    'studio.install_update_package': 1800,
    'studio.resume_update': 1800,
    'studio.rollback_update': 1800,
}


def defaults():
    return dict(sorted((tool, LONGER.get(tool, DEFAULT_SECONDS)) for tool in {
        entry['name'].replace('studio_', 'studio.', 1) for tools in catalog().values() for entry in tools
    }))


def present(tool, seconds, revision, default):
    return {'id': tool, 'seconds': default if seconds is None else seconds, 'revision': revision,
            'defaultSeconds': default, 'overridden': seconds is not None}


def saved(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version == 0 and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
        return {}
    if version != 1:
        raise ProjectFault('Tool deadline settings storage is unavailable.', 503)
    return {tool: (seconds, revision) for tool, seconds, revision
            in db.execute('SELECT tool,seconds,revision FROM global_tool_deadlines')}


def read(projects):
    path = location(projects, kind='tools')
    values = {}
    if path.exists():
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
            db.execute('BEGIN')
            values = saved(db)
    return {'minSeconds': MIN_SECONDS, 'maxSeconds': MAX_SECONDS,
            'tools': [present(tool, *values.get(tool, (None, 0)), default) for tool, default in defaults().items()]}


def update(projects, data):
    if not isinstance(data, dict) or set(data) != {'tool', 'seconds', 'revision'}:
        raise ProjectFault('Invalid tool deadline settings.', 400)
    tool, seconds, revision = data['tool'], data['seconds'], data['revision']
    known = defaults()
    if (not isinstance(tool, str) or tool not in known or type(revision) is not int or not 0 <= revision < 2**53-1
            or seconds is not None and (type(seconds) is not int or not MIN_SECONDS <= seconds <= MAX_SECONDS)):
        raise ProjectFault('Choose a Studio tool and a whole number from 1 to 7200 seconds.', 400)
    default = known[tool]
    desired = None if seconds == default else seconds
    path = location(projects, create=True, kind='tools')
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        os.chmod(path, 0o600)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        schema = db.execute('PRAGMA user_version').fetchone()[0]
        if schema == 0 and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
            db.execute('''CREATE TABLE global_tool_deadlines (
                tool TEXT PRIMARY KEY, seconds INTEGER CHECK(seconds BETWEEN 1 AND 7200),
                revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991))''')
            db.execute('PRAGMA user_version=1')
        elif schema != 1:
            raise ProjectFault('Unsupported tool deadline settings.', 503)
        previous, actual = db.execute('SELECT seconds,revision FROM global_tool_deadlines WHERE tool=?',
                                      (tool,)).fetchone() or (None, 0)
        if desired != previous:
            if revision != actual:
                raise ProjectFault('This tool deadline changed. Reload settings before saving.', 409)
            actual += 1
            db.execute('''INSERT INTO global_tool_deadlines VALUES (?,?,?)
                ON CONFLICT(tool) DO UPDATE SET seconds=excluded.seconds,revision=excluded.revision''',
                (tool, desired, actual))
        return present(tool, desired, actual, default)


def freeze(projects):
    return {'version': 1, 'seconds': {item['id']: item['seconds'] for item in read(projects)['tools']}}


def seconds_for(config, tool):
    frozen = config.get('toolDeadlines', {})
    if frozen.get('version') == 1:
        return frozen['seconds'][tool]
    return None
