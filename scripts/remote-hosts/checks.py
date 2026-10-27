"""Durable, secret-free connection-check intents and original result receipts."""
import hashlib
import json
import os
from pathlib import Path
import uuid
from catalog import connection, CatalogFault, fields, identity, integer, now, public, regular, sync
from transport import private_directory


def root(directory): return private_directory(Path(directory) / 'Tests')


def read(path):
    if path.resolve(strict=True) != path.absolute(): raise CatalogFault('Invalid original connection check.', 503)
    regular(path)
    if path.stat().st_size > 32768: raise CatalogFault('Connection check metadata exceeds its limit.', 503)
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or value.get('phase') not in ('accepted', 'connecting', 'complete', 'unknown') or value.get('requestId') != path.parent.name:
        raise CatalogFault('Connection check metadata needs local maintenance.', 503)
    return value


def save(path, value):
    encoded = json.dumps(value, ensure_ascii=True)
    if len(encoded.encode('utf8')) > 32768: raise CatalogFault('Connection check metadata exceeds its limit.', 503)
    if path.parent.resolve(strict=True) != path.parent: raise CatalogFault('Invalid original check storage.', 503)
    if path.exists() or path.is_symlink():
        original = read(path)
        if any(original.get(k) != value.get(k) for k in ('requestId', 'hostId', 'fingerprint')): raise CatalogFault('The original check journal changed. Existing data was preserved.', 503)
    stages = list(path.parent.glob('.record-*.tmp'))
    if len(stages) >= 8: raise CatalogFault('Interrupted check writes need local maintenance. Their original stages were preserved.', 503)
    temporary = path.with_name('.record-' + str(uuid.uuid4()) + '.tmp')
    with temporary.open('x', encoding='utf8') as stream:
        os.chmod(temporary, 0o600); stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path); sync(path.parent)


def path_for(directory, request): return root(directory) / identity(request) / 'check.json'


def active(directory, host_id):
    folder = Path(directory) / 'Tests'
    if not folder.exists() and not folder.is_symlink(): return False
    folder = root(directory); entries = list(folder.iterdir())
    if len(entries) > 1000: raise CatalogFault('Connection check history needs local maintenance.', 503)
    for entry in entries:
        identity(entry.name)
        value = read(entry / 'check.json')
        if value['hostId'] == host_id and value['phase'] in ('accepted', 'connecting'): return True
    return False


def binding(row): return {k: row[k] for k in ('id', 'endpointRevision', 'credentialRevision', 'trustRevision')}


def begin(directory, host_id, data):
    identity(host_id); fields(data, ['requestId', 'revision']); identity(data['requestId']); integer(data['revision'])
    fingerprint = hashlib.sha256(json.dumps({'operation': 'test', 'hostId': host_id, **data}, sort_keys=True).encode()).hexdigest()
    with connection(directory) as db:
        if db is None: raise CatalogFault('Remote Host was removed.', 404)
        path = path_for(directory, data['requestId'])
        if path.exists() or path.is_symlink():
            previous = read(path)
            if previous['fingerprint'] != fingerprint: raise CatalogFault('This request ID belongs to another connection check.')
            confirmed = db.execute('SELECT fingerprint,result FROM receipts WHERE request_id=?', (data['requestId'],)).fetchone()
            if confirmed:
                if confirmed['fingerprint'] != fingerprint: raise CatalogFault('The original connection receipt conflicts.', 503)
                result = json.loads(confirmed['result']); save(path, result); return result
            return previous
        if db.execute('SELECT 1 FROM receipts WHERE request_id=?', (data['requestId'],)).fetchone(): raise CatalogFault('This request ID already belongs to catalog management.')
        if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 10000: raise CatalogFault('Remote request history needs local maintenance.', 503)
        host = public(db, db.execute('SELECT * FROM hosts WHERE id=?', (host_id,)).fetchone())
        if host['revision'] != data['revision']: raise CatalogFault('Host settings changed. Reload before checking this host.')
        if active(directory, host_id): raise CatalogFault('A connection check is already active for this host.')
        if len(list(path.parent.parent.iterdir())) >= 1000: raise CatalogFault('Connection check history is full.', 503)
        private_directory(path.parent)
        value = {'schema': 1, 'requestId': data['requestId'], 'hostId': host_id, 'fingerprint': fingerprint,
                 'binding': binding(host), 'phase': 'accepted', 'createdAt': now(), 'updatedAt': now()}
        save(path, value); sync(path.parent.parent); return value


def target(directory, value):
    with connection(directory) as db:
        if db is None: raise CatalogFault('Remote Host was removed.', 404)
        row = db.execute('SELECT * FROM hosts WHERE id=?', (value['hostId'],)).fetchone(); host = public(db, row)
        if binding(host) != value['binding']: raise CatalogFault('The original remote target binding changed.')
        secret = db.execute('SELECT password FROM secrets WHERE host_id=?', (host['id'],)).fetchone()
        if secret is None: raise CatalogFault('No password is configured for this host.')
        key = dict(db.execute('SELECT * FROM host_keys WHERE host_id=?', (host['id'],)).fetchone())
        return {**host, 'password': secret['password'], 'key': key}


def finish(directory, value, outcome):
    path = path_for(directory, value['requestId']); value = {**value, 'phase': 'complete', 'updatedAt': now()}
    with connection(directory) as db:
        if db is None: raise CatalogFault('The original catalog is unavailable.', 503)
        confirmed = db.execute('SELECT fingerprint,result FROM receipts WHERE request_id=?', (value['requestId'],)).fetchone()
        if confirmed:
            if confirmed['fingerprint'] != value['fingerprint']: raise CatalogFault('The original connection receipt conflicts.', 503)
            result = json.loads(confirmed['result']); save(path, result); return result
        host = public(db, db.execute('SELECT * FROM hosts WHERE id=?', (value['hostId'],)).fetchone())
        if binding(host) != value['binding']:
            value.update(invalidated=True, host=host); save(path, value); return value
        # A first explicitly requested check binds the observed host identity,
        # including on authentication failure. This is TOFU, not independent trust.
        key = outcome.get('key'); stamp = now(); trust = host['trustRevision']
        if key and host['hostKey']['state'] == 'trusted' and key['fingerprint'] != host['hostKey']['fingerprint']:
            outcome = {'status': 'hostkey_changed'}; key = None
        db.execute('BEGIN IMMEDIATE')
        if key and host['hostKey']['state'] == 'unbound':
            trust += 1
            db.execute("UPDATE host_keys SET state='trusted',key_type=?,key_data=?,fingerprint=?,trusted_at=? WHERE host_id=?", (key['keyType'], key['keyData'], key['fingerprint'], stamp, host['id']))
        result = {'status': outcome['status'], 'checkedAt': stamp, 'endpointRevision': host['endpointRevision'],
                  'credentialRevision': host['credentialRevision'], 'trustRevision': trust,
                  **{k: outcome[k] for k in ('version', 'kernel') if k in outcome}}
        db.execute('UPDATE hosts SET revision=revision+1,trust_revision=?,last_test=?,updated_at=? WHERE id=?', (trust, json.dumps(result), stamp, host['id']))
        value['host'] = public(db, db.execute('SELECT * FROM hosts WHERE id=?', (host['id'],)).fetchone())
        db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (value['requestId'], value['fingerprint'], json.dumps(value), stamp))
        db.commit()
        save(path, value); return value


def status(directory, host_id, request_id):
    value = read(path_for(directory, request_id))
    if value['hostId'] != identity(host_id): raise CatalogFault('This connection check belongs to another host.', 404)
    with connection(directory) as db:
        if db:
            confirmed = db.execute('SELECT fingerprint,result FROM receipts WHERE request_id=?', (request_id,)).fetchone()
            if confirmed:
                if confirmed['fingerprint'] != value['fingerprint']: raise CatalogFault('The original check receipt conflicts.', 503)
                value = json.loads(confirmed['result'])
    return {k: v for k, v in value.items() if k not in ('schema', 'fingerprint', 'binding')}


def recover(directory):
    folder = Path(directory) / 'Tests'
    if not folder.exists(): return
    for entry in root(directory).iterdir():
        value = read(entry / 'check.json')
        if value['phase'] not in ('accepted', 'connecting'): continue
        original = status(directory, value['hostId'], value['requestId'])
        if original['phase'] == 'complete':
            with connection(directory) as db:
                result = json.loads(db.execute('SELECT result FROM receipts WHERE request_id=?', (value['requestId'],)).fetchone()[0])
            save(entry / 'check.json', result)
        else: save(entry / 'check.json', {**value, 'phase': 'unknown', 'updatedAt': now(), 'message': 'The original check was interrupted. No connection was repeated and current readiness is not confirmed.'})
