"""Optional GitHub sources. Configuration never downloads or executes a repository."""
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit


def normalize(value, fault):
    if value is None:
        return None
    fields = {'repository', 'ref', 'skillPath', 'recipe', 'connectionId'}
    if not isinstance(value, dict) or set(value) - fields or 'repository' not in value:
        raise fault('Use a GitHub repository, ref and relative skill path.', 400)
    url = value['repository']
    if not isinstance(url, str) or len(url) > 512 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise fault('Enter an HTTPS GitHub repository URL.', 400)
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise fault('Invalid GitHub repository URL.', 400) from None
    if (parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com' or parsed.query or parsed.fragment
            or not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?', parsed.path)):
        raise fault('Use https://github.com/owner/repository; specify ref and skill path separately.', 400)
    owner, repo = parsed.path.strip('/').split('/')
    if repo.endswith('.git'):
        repo = repo[:-4]
    if owner in ('.', '..') or not repo or repo in ('.', '..'):
        raise fault('Invalid GitHub repository.', 400)
    repository = 'https://github.com/' + owner.lower() + '/' + repo.lower()
    ref = value.get('ref', '')
    if (not isinstance(ref, str) or len(ref) > 240 or any(ord(c) < 33 or ord(c) == 127 for c in ref)
            or any(c in ref for c in ('..', '@{', '\\', '~', '^', ':', '?', '*', '[', '//'))
            or ref.startswith(('/', '-', '.')) or ref.endswith(('/', '.'))
            or any(part.endswith('.lock') or part.startswith('.') for part in ref.split('/') if part)):
        raise fault('Enter a branch, tag or commit without Git options or revision expressions.', 400)
    rea = repository == 'https://github.com/morluto/rea'
    path = value.get('skillPath', '.agents/skills/reverse-engineer-anything' if rea else '')
    if (not isinstance(path, str) or len(path) > 240 or '\\' in path
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or path and (str(PurePosixPath(path)) != path or PurePosixPath(path).is_absolute()
                         or any(p in ('.', '..') for p in PurePosixPath(path).parts))):
        raise fault('Skill path must be a relative directory within the repository.', 400)
    recipe = value.get('recipe', 'rea' if rea else None)
    if recipe is not None and (recipe != 'rea' or not rea):
        raise fault('This repository has no managed runtime recipe.', 400)
    connection = value.get('connectionId')
    if connection is not None and (not isinstance(connection, str) or not re.fullmatch(
            '[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', connection)):
        raise fault('Invalid GitHub connection.', 400)
    return dict(repository=repository, ref=ref, skillPath=path, recipe=recipe, connectionId=connection)


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS skill_sources(skill_id TEXT PRIMARY KEY,metadata TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS skill_source_requests(
        request_id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS skill_source_jobs(
        request_id TEXT PRIMARY KEY,skill_id TEXT NOT NULL,fingerprint TEXT NOT NULL,metadata TEXT NOT NULL)''')


def read(db, ident):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_sources'").fetchone():
        return None
    row = db.execute('SELECT metadata FROM skill_sources WHERE skill_id=?', (ident,)).fetchone()
    return json.loads(row[0]) if row else None


def configure(db, root, data, api):
    if (not isinstance(data, dict) or set(data) != {'id', 'revision', 'source', 'requestId'}
            or type(data['revision']) is not int or data['revision'] < 1):
        raise api.SkillFault('Invalid skill source request.', 400)
    ident = api.identity(data['id'])
    api.identity(data['requestId'])
    source = normalize(data['source'], api.SkillFault)
    fingerprint = api.digest(api.encode(data).encode())
    with api.locked(root, ident):
        schema(db)
        previous = db.execute('SELECT * FROM skill_source_requests WHERE request_id=?', (data['requestId'],)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise api.SkillFault('This source request ID has already been used.', 409)
            return json.loads(previous['result'])
        current = api.detail(db, root, ident)
        if current['skill']['revision'] != data['revision']:
            raise api.SkillFault('The skill changed. Reload before changing its source.', 409)
        old = read(db, ident)
        if old and old.get('lastRequestId'):
            job = read_job(db, ident, old['lastRequestId'], api)
            if job['phase'] not in ('complete', 'failed', 'cancelled'):
                raise api.SkillFault('Observe or finish the original source operation before changing its configuration.', 423)
        metadata = None
        if source is not None:
            metadata = dict(configuration=source, revision=(old['revision'] if old else 0) + 1,
                            status='configured', commit=None, active=old.get('active') if old else None,
                            lastRequestId=None, updatedAt=api.now())
            # These paths remain private data and are never package resources.
            for name in ('Sources', 'Runtimes'):
                api.folder(root / ident / name, True)
        db.execute('BEGIN IMMEDIATE')
        if metadata is None:
            db.execute('DELETE FROM skill_sources WHERE skill_id=?', (ident,))
        else:
            db.execute('INSERT OR REPLACE INTO skill_sources VALUES(?,?)', (ident, api.encode(metadata)))
        db.execute('UPDATE skills SET revision=revision+1,updated_at=? WHERE id=?', (api.now(), ident))
        result = api.detail(db, root, ident)
        db.execute('INSERT INTO skill_source_requests VALUES(?,?,?)',
                   (data['requestId'], fingerprint, api.encode(result)))
        db.commit()
        return result


def read_job(db, ident, request_id, api):
    api.identity(ident)
    api.identity(request_id)
    row = None
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_source_jobs'").fetchone():
        row = db.execute('SELECT metadata FROM skill_source_jobs WHERE request_id=? AND skill_id=?',
                         (request_id, ident)).fetchone()
    if not row:
        raise api.SkillFault('This skill source operation is unavailable.', 404)
    return json.loads(row[0])


def prepare(db, root, data, api):
    fields = {'id', 'revision', 'sourceRevision', 'draftHash', 'requestId', 'action'}
    if (not isinstance(data, dict) or set(data) != fields or type(data['revision']) is not int
            or type(data['sourceRevision']) is not int or data['action'] not in ('activate', 'update')):
        raise api.SkillFault('Invalid source activation request.', 400)
    ident = api.identity(data['id'])
    api.identity(data['requestId'])
    fingerprint = api.digest(api.encode(data).encode())
    with api.locked(root, ident):
        schema(db)
        previous = db.execute('SELECT * FROM skill_source_jobs WHERE request_id=?', (data['requestId'],)).fetchone()
        if previous:
            if previous['skill_id'] != ident or previous['fingerprint'] != fingerprint:
                raise api.SkillFault('This source operation ID has already been used.', 409)
            return json.loads(previous['metadata'])
        current = api.detail(db, root, ident)
        source = read(db, ident)
        if not source:
            raise api.SkillFault('Configure a GitHub source before activating it.', 409)
        if (current['skill']['revision'] != data['revision'] or source['revision'] != data['sourceRevision']
                or current['draftHash'] != data['draftHash']):
            raise api.SkillFault('The source or skill draft changed. Reload before activating it.', 409)
        if source.get('lastRequestId'):
            old = read_job(db, ident, source['lastRequestId'], api)
            if old['phase'] not in ('complete', 'failed', 'cancelled'):
                raise api.SkillFault('Observe the original source operation before starting another.', 423)
        stamp = api.now()
        job = dict(requestId=data['requestId'], skillId=ident, action=data['action'], phase='queued',
                   sourceRevision=source['revision'], skillRevision=data['revision'], draftHash=data['draftHash'],
                   configuration=source['configuration'], createdAt=stamp, updatedAt=stamp,
                   commit=None, pid=None, result=None, error=None)
        source.update(status='queued', lastRequestId=data['requestId'], updatedAt=stamp)
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO skill_source_jobs VALUES(?,?,?,?)',
                   (data['requestId'], ident, fingerprint, api.encode(job)))
        db.execute('UPDATE skill_sources SET metadata=? WHERE skill_id=?', (api.encode(source), ident))
        db.commit()
        return job
