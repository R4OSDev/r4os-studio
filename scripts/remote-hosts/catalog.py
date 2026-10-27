"""Private global inventory. Local management never opens network connections."""
from contextlib import contextmanager, closing
import ctypes
from datetime import datetime, timezone
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import unicodedata
import uuid

APPLICATION_ID = 0x52345248
MAX_BYTES = 64 * 1024**2
SCHEMA = '''
CREATE TABLE hosts(id TEXT PRIMARY KEY,name TEXT NOT NULL,name_fold TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL,address TEXT NOT NULL,port INTEGER NOT NULL,user TEXT NOT NULL,
 revision INTEGER NOT NULL,endpoint_revision INTEGER NOT NULL,credential_revision INTEGER NOT NULL,
 trust_revision INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,last_test TEXT);
CREATE TABLE secrets(host_id TEXT PRIMARY KEY REFERENCES hosts(id) ON DELETE CASCADE,password TEXT NOT NULL);
CREATE TABLE host_keys(host_id TEXT PRIMARY KEY REFERENCES hosts(id) ON DELETE CASCADE,
 state TEXT NOT NULL,key_type TEXT,key_data TEXT,fingerprint TEXT,trusted_at TEXT);
CREATE TABLE receipts(request_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE retired(id TEXT PRIMARY KEY,deleted_at TEXT NOT NULL);
PRAGMA application_id=1379160648;
PRAGMA user_version=1;
'''


class CatalogFault(Exception):
    def __init__(self, message, code=409): super().__init__(message); self.code = code


def fields(value, required=(), optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or set(value) - set(required) - set(optional):
        raise CatalogFault('Unexpected Remote Host request fields.', 400)
    return value


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', value):
        raise CatalogFault('Invalid Remote Host identity.', 400)
    return value


def text(value, maximum, required=False):
    if (not isinstance(value, str) or len(value.encode('utf8')) > maximum
            or any(unicodedata.category(c).startswith('C') and c not in '\t\n\r' for c in value)
            or (required and not value.strip())):
        raise CatalogFault('Enter valid text within the Remote Host field limits.', 400)
    return value.strip() if required else value


def host_address(value):
    if not isinstance(value, str) or not value or len(value) > 253 or value != value.strip() or '%' in value:
        raise CatalogFault('Enter a DNS name, IPv4 address or IPv6 address without a URL or options.', 400)
    try: return str(ipaddress.ip_address(value))
    except ValueError: pass
    # Literal unbracketed IPv6 is handled above. No zone IDs, URLs, ports,
    # whitespace, SSH user prefixes or local option syntax are accepted.
    value = value.removesuffix('.').lower()
    if not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.')):
        raise CatalogFault('Enter a DNS name, IPv4 address or IPv6 address without a URL or options.', 400)
    if re.fullmatch(r'[0-9.]+', value): raise CatalogFault('Enter a valid IP address.', 400)
    return value


def integer(value, maximum=2147483647):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise CatalogFault('Enter a valid revision or SSH port.', 400)
    return value


def changes(value):
    result = {}
    for key, item in value.items():
        if key == 'name':
            name = unicodedata.normalize('NFC', text(item, 240, True))
            if any(c in name for c in '\n\r\t'): raise CatalogFault('Enter a single-line host name.', 400)
            result[key] = name
        elif key == 'description': result[key] = text(item, 4000)
        elif key == 'address': result[key] = host_address(item)
        elif key == 'port': result[key] = integer(item, 65535)
        elif key == 'user':
            if not isinstance(item, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}', item): raise CatalogFault('Enter an SSH user of up to 64 letters, digits, underscores, dots or hyphens.', 400)
            result[key] = item
        elif key == 'password':
            if not isinstance(item, str) or not 1 <= len(item.encode('utf8')) <= 4096 or any(ord(c) < 32 or ord(c) == 127 for c in item): raise CatalogFault('Enter a password of 1–4096 UTF-8 bytes without control characters.', 400)
            result[key] = item
    return result


def now(): return datetime.now(timezone.utc).isoformat()


def regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > MAX_BYTES:
        raise CatalogFault('Remote Host storage needs local host maintenance. Existing data was preserved.', 503)


def sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


@contextmanager
def connection(directory, initialize=False):
    directory = Path(directory).absolute()
    if directory.parent.resolve(strict=True) != directory.parent:
        raise CatalogFault('Remote Host storage needs a real Data directory.', 503)
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if directory.resolve(strict=True) != directory or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise CatalogFault('Remote Host storage needs local host maintenance. Existing data was preserved.', 503)
    fd = os.open(directory / '.catalog.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    db = None
    try:
        regular(directory / '.catalog.lock')
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise CatalogFault('Remote Host storage is busy. Retry the original request.') from None
        path = directory / 'RemoteHosts.sqlite'
        if not path.exists() and not path.is_symlink():
            if not initialize: yield None; return
            temporary = directory / ('.initial-' + str(uuid.uuid4()) + '.sqlite')
            with closing(sqlite3.connect(temporary)) as fresh:
                fresh.executescript(SCHEMA)
            os.chmod(temporary, 0o600)
            with temporary.open('rb') as stream: os.fsync(stream.fileno())
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.renameat2(-100, os.fsencode(temporary), -100, os.fsencode(path), 1) != 0:
                raise CatalogFault('Remote Host initialization could not be confirmed. Preserve its staged data.', 503)
            sync(directory)
        regular(path)
        for suffix in ('-journal', '-wal', '-shm'):
            sidecar = path.with_name(path.name + suffix)
            if sidecar.exists() or sidecar.is_symlink(): regular(sidecar)
        db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=3)
        db.row_factory = sqlite3.Row
        if db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise CatalogFault('Remote Host schema requires a matching release. Existing data was preserved.', 503)
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA secure_delete=ON')
        if db.execute('PRAGMA quick_check(1)').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise CatalogFault('Remote Host inventory is damaged. Existing data was preserved.', 503)
        yield db
    finally:
        if db: db.close()
        os.close(fd)


def public(db, row):
    if row is None: raise CatalogFault('Remote Host is missing or was removed.', 404)
    key = db.execute('SELECT state,fingerprint,trusted_at FROM host_keys WHERE host_id=?', (row['id'],)).fetchone()
    if key is None: raise CatalogFault('Remote Host trust metadata needs local maintenance.', 503)
    values = changes({k: row[k] for k in ('name', 'description', 'address', 'port', 'user')})
    identity(row['id'])
    if any(values[k] != row[k] for k in values) or row['name_fold'] != row['name'].casefold() or key['state'] not in ('unbound', 'trusted'):
        raise CatalogFault('Remote Host metadata needs local maintenance.', 503)
    for column in ('revision', 'endpoint_revision', 'credential_revision', 'trust_revision'): integer(row[column])
    last_test = None
    if row['last_test']:
        stored = json.loads(row['last_test'])
        allowed = ('status', 'checkedAt', 'endpointRevision', 'credentialRevision', 'trustRevision', 'version', 'kernel')
        if not isinstance(stored, dict) or set(stored) - set(allowed) or stored.get('status') not in ('success', 'offline', 'authentication_failed', 'hostkey_changed', 'not_r4os', 'transport_error', 'timeout'):
            raise CatalogFault('Remote Host test metadata needs local maintenance.', 503)
        last_test = {k: stored[k] for k in allowed if k in stored}
    return {'id': row['id'], **{k: row[k] for k in ('name', 'description', 'address', 'port', 'user', 'revision')},
            'endpointRevision': row['endpoint_revision'], 'credentialRevision': row['credential_revision'], 'trustRevision': row['trust_revision'],
            'passwordConfigured': db.execute('SELECT 1 FROM secrets WHERE host_id=?', (row['id'],)).fetchone() is not None,
            'hostKey': {'state': key['state'], 'fingerprint': key['fingerprint'], 'trustedAt': key['trusted_at']},
            'lastTest': last_test, 'createdAt': row['created_at'], 'updatedAt': row['updated_at']}


def operation(directory, request):
    fields(request, ['operation'], ['id', 'input'])
    op = request['operation']
    if op not in ('list', 'get', 'create', 'update', 'remove', 'reset_trust'): raise CatalogFault('Unsupported Remote Host operation.', 400)
    fields(request, ['operation', *(['id'] if op in ('get', 'update', 'remove', 'reset_trust') else []), *(['input'] if op in ('create', 'update', 'remove', 'reset_trust') else [])])
    ident = identity(request['id']) if 'id' in request else None
    data = request.get('input')
    if op == 'create':
        fields(data, ['requestId', 'name', 'address'], ['description', 'port', 'user', 'password'])
        content = changes({'description': '', 'port': 22, 'user': 'r4os', 'password': 'rosebud', **data})
    elif op == 'update':
        fields(data, ['requestId', 'revision'], ['name', 'description', 'address', 'port', 'user', 'password']); integer(data['revision'])
        content = changes(data)
        if not content: raise CatalogFault('No Remote Host changes were supplied.', 400)
    elif op in ('remove', 'reset_trust'):
        fields(data, ['requestId', 'revision', 'confirm']); integer(data['revision'])
        if data['confirm'] is not True: raise CatalogFault('Confirm this local Remote Host change.', 400)
    if data is not None:
        identity(data['requestId']); fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
    with connection(directory, initialize=op == 'create') as db:
        if op == 'list': return [] if db is None else [public(db, r) for r in db.execute('SELECT * FROM hosts ORDER BY name_fold,id')]
        if op == 'get': return public(db, None if db is None else db.execute('SELECT * FROM hosts WHERE id=?', (ident,)).fetchone())
        if db is None: raise CatalogFault('Remote Host is missing or was removed.', 404)
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT * FROM receipts WHERE request_id=?', (data['requestId'],)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint: raise CatalogFault('This request ID belongs to different Remote Host input.')
            return json.loads(previous['result'])
        check = Path(directory) / 'Tests' / data['requestId'] / 'check.json'
        if check.exists() or check.is_symlink(): raise CatalogFault('This request ID belongs to an original connection check.')
        if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 10000: raise CatalogFault('Remote Host request history needs local maintenance.', 503)
        stamp = now()
        if op == 'create':
            if db.execute('SELECT count(*) FROM hosts').fetchone()[0] >= 1000: raise CatalogFault('The Remote Host catalog is full.', 409)
            ident = str(uuid.uuid4())
            db.execute('INSERT INTO hosts VALUES (?,?,?,?,?,?,?,1,1,1,1,?,?,NULL)', (ident, content['name'], content['name'].casefold(), content['description'], content['address'], content['port'], content['user'], stamp, stamp))
            db.execute('INSERT INTO secrets VALUES (?,?)', (ident, content['password']))
            db.execute("INSERT INTO host_keys VALUES (?,'unbound',NULL,NULL,NULL,NULL)", (ident,))
        else:
            row = db.execute('SELECT * FROM hosts WHERE id=?', (ident,)).fetchone()
            if row is None: raise CatalogFault('Remote Host is missing or was removed.', 404)
            if row['revision'] != data['revision']: raise CatalogFault('Remote Host settings changed. Reload saved values; your input has been retained.')
            from checks import active
            target_change = op in ('remove', 'reset_trust') or (op == 'update' and ('password' in content or any(content.get(k, row[k]) != row[k] for k in ('address', 'port', 'user'))))
            if target_change and active(directory, ident): raise CatalogFault('Wait for the original connection check before changing its target, login or trust.')
            if op == 'remove':
                db.execute('INSERT INTO retired VALUES (?,?)', (ident, stamp)); db.execute('DELETE FROM hosts WHERE id=?', (ident,))
            elif op == 'reset_trust':
                db.execute("UPDATE host_keys SET state='unbound',key_type=NULL,key_data=NULL,fingerprint=NULL,trusted_at=NULL WHERE host_id=?", (ident,))
                db.execute('UPDATE hosts SET revision=revision+1,trust_revision=trust_revision+1,last_test=NULL,updated_at=? WHERE id=?', (stamp, ident))
            else:
                endpoint = any(content.get(k, row[k]) != row[k] for k in ('address', 'port'))
                credential = content.get('user', row['user']) != row['user'] or 'password' in content
                for key in ('name', 'description', 'address', 'port', 'user'):
                    if key in content: db.execute('UPDATE hosts SET ' + key + '=? WHERE id=?', (content[key], ident))
                if 'name' in content: db.execute('UPDATE hosts SET name_fold=? WHERE id=?', (content['name'].casefold(), ident))
                if 'password' in content: db.execute('UPDATE secrets SET password=? WHERE host_id=?', (content['password'], ident))
                db.execute('UPDATE hosts SET revision=revision+1,endpoint_revision=endpoint_revision+?,credential_revision=credential_revision+?,trust_revision=trust_revision+?,updated_at=?,last_test=CASE WHEN ? THEN NULL ELSE last_test END WHERE id=?', (int(endpoint), int(credential), int(endpoint), stamp, int(endpoint or credential), ident))
                if endpoint: db.execute("UPDATE host_keys SET state='unbound',key_type=NULL,key_data=NULL,fingerprint=NULL,trusted_at=NULL WHERE host_id=?", (ident,))
        result = {'id': ident, 'removed': True} if op == 'remove' else public(db, db.execute('SELECT * FROM hosts WHERE id=?', (ident,)).fetchone())
        db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (data['requestId'], fingerprint, json.dumps(result, ensure_ascii=True), stamp))
        db.commit(); return result
