"""Small strict contracts; identifiers never select host paths or SQL names."""
import re
from storage import RoadmapFault

KINDS = {'roadmap': 'roadmap', 'version': 'versions', 'subversion': 'subversions',
         'task': 'tasks', 'acceptance': 'acceptances'}
UUID = re.compile(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}')


def fields(value, required=(), optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise RoadmapFault('Unexpected roadmap fields.', 400)
    return value


def identity(value):
    if not isinstance(value, str) or not UUID.fullmatch(value):
        raise RoadmapFault('Invalid roadmap identity.', 400)
    return value


def integer(value, minimum=0, maximum=2147483647):
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise RoadmapFault('Invalid roadmap number or revision.', 400)
    return value


def text(value, maximum=32768, required=False):
    if (not isinstance(value, str) or len(value.encode('utf-8')) > maximum
            or any(ord(c) == 127 or (ord(c) < 32 and c not in '\t\r\n') for c in value)
            or (required and not value.strip())):
        raise RoadmapFault('Enter valid roadmap text within the size limit.', 400)
    return value.strip() if required else value


def number(value, version=None):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(X|0|[1-9][0-9]*)', value):
        raise RoadmapFault('Use a canonical roadmap version number, for example 0.1.X or 0.1.1.', 400)
    major, minor, patch = value.split('.')
    major, minor = integer(int(major)), integer(int(minor))
    if version is None:
        if patch != 'X':
            raise RoadmapFault('A main version number must end in .X.', 400)
        return major, minor
    if patch == 'X' or (major, minor) != (version['major'], version['minor']):
        raise RoadmapFault('The subversion number must belong to its selected main version.', 400)
    return integer(int(patch))


def target(db, value, needs_id=True):
    kind = value.get('kind') if isinstance(value, dict) else None
    if not isinstance(kind, str) or kind not in KINDS:
        raise RoadmapFault('Invalid roadmap target.', 400)
    parents = ['versionId'] if kind == 'subversion' else ['versionId', 'subversionId'] if kind in ('task', 'acceptance') else []
    fields(value, ['kind', *parents, *(['id'] if needs_id else [])])
    for key in [*parents, *(['id'] if needs_id else [])]:
        identity(value[key])
    if 'versionId' in value and not db.execute('SELECT id FROM versions WHERE id=?', (value['versionId'],)).fetchone():
        raise RoadmapFault('Main version not found in this project.', 404)
    if 'subversionId' in value and not db.execute('SELECT id FROM subversions WHERE id=? AND version_id=?',
                                                (value['subversionId'], value['versionId'])).fetchone():
        raise RoadmapFault('Subversion not found in this main version.', 404)
    if not needs_id:
        return None
    table = KINDS[kind]
    row = db.execute('SELECT * FROM ' + table + ' WHERE id=?', (value['id'],)).fetchone()
    if row is None or (kind == 'subversion' and row['version_id'] != value['versionId']) or (
            kind in ('task', 'acceptance') and row['subversion_id'] != value['subversionId']):
        raise RoadmapFault('Roadmap entry not found under the selected parent.', 404)
    return row
