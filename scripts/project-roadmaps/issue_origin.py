"""Verified issue import and its project-private Roadmap provenance."""
import hashlib
import json
import re
import sqlite3
from urllib.parse import urlsplit

from mutations import create
from reads import binding, root_row
from storage import RoadmapFault, timestamp
from validation import fields, identity, integer, text


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS github_issue_origins (
        repository_id INTEGER NOT NULL,
        issue_id TEXT NOT NULL,
        issue_number INTEGER NOT NULL,
        issue_url TEXT NOT NULL,
        subversion_id TEXT NOT NULL UNIQUE REFERENCES subversions(id) ON DELETE CASCADE,
        acceptance_id TEXT NOT NULL UNIQUE REFERENCES acceptances(id) ON DELETE CASCADE,
        PRIMARY KEY(repository_id,issue_id), UNIQUE(repository_id,issue_number)
    )''')


def available(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='github_issue_origins'").fetchone() is not None


def record_closure(db, subversion_id, receipt):
    db.execute('''CREATE TABLE IF NOT EXISTS github_issue_closures (
        subversion_id TEXT PRIMARY KEY REFERENCES github_issue_origins(subversion_id) ON DELETE CASCADE,
        request_id TEXT NOT NULL, reason TEXT NOT NULL,
        comment_url TEXT NOT NULL, closed_at TEXT NOT NULL
    )''')
    db.execute('INSERT OR REPLACE INTO github_issue_closures VALUES(?,?,?,?,?)',
               (subversion_id,receipt['requestId'],receipt['reason'],receipt['comment']['url'],receipt['closedAt']))


def closure(db, subversion_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='github_issue_closures'").fetchone():
        return None
    return db.execute('SELECT * FROM github_issue_closures WHERE subversion_id=?',(subversion_id,)).fetchone()


def guard_change(db, kind, row, action, value):
    if kind not in ('subversion','acceptance') or not available(db):
        return
    if kind=='subversion':
        if value.get('status') not in ('complete','discarded'):
            return
        subversion_id=row['id']
        if not origin(db,subversion_id):
            return
        if value['status']=='discarded':
            if row['status']=='discarded': return
            raise RoadmapFault('Use Discard on the linked GitHub issue to record its closure.',409)
    else:
        subversion_id=row['subversion_id']
        source=origin(db,subversion_id)
        if not source or source['acceptanceId']!=row['id']:
            return
        if action=='delete':
            raise RoadmapFault('The imported GitHub acceptance belongs to this linked subversion.',409)
        status=value.get('status')
        if status not in ('done','discarded'):
            return
        if status=='discarded':
            if row['status']=='discarded': return
            raise RoadmapFault('Use Discard on the linked GitHub issue to record its closure.',409)
    outcome=closure(db,subversion_id)
    if not outcome or outcome['reason']!='COMPLETED':
        raise RoadmapFault('Confirm the linked GitHub comment and Completed closure before marking this work complete.',409)


def public(row):
    return {'repositoryId': row['repository_id'], 'issueId': row['issue_id'], 'number': row['issue_number'],
            'url': row['issue_url'], 'acceptanceId': row['acceptance_id']}


def origin(db, subversion_id):
    if not available(db):
        return None
    row = db.execute('SELECT * FROM github_issue_origins WHERE subversion_id=?', (subversion_id,)).fetchone()
    return public(row) if row else None


def source_fields(db, subversion_id):
    source = origin(db, subversion_id)
    return {'githubIssue': source} if source else {}


def linked(db, repository_id, numbers):
    if not numbers or not available(db):
        return {}
    placeholders = ','.join('?' for _ in numbers)
    rows = db.execute('''SELECT i.*, s.version_id FROM github_issue_origins i
        JOIN subversions s ON s.id=i.subversion_id WHERE i.repository_id=? AND i.issue_number IN (''' + placeholders + ')',
        (repository_id, *numbers))
    return {str(row['issue_number']): {'versionId': row['version_id'], 'subversionId': row['subversion_id'],
            'issueId': row['issue_id']} for row in rows}


def selection(db, body):
    fields(body, ['repositoryId', 'numbers'])
    repository_id = integer(body['repositoryId'], 1, 2**53-1)
    numbers = body['numbers']
    if not isinstance(numbers, list) or len(numbers) > 25:
        raise RoadmapFault('Select one page of GitHub issues.', 400)
    numbers = [integer(n, 1, 2**53-1) for n in numbers]
    return {'links': linked(db, repository_id, numbers) if db is not None else {}}


def normalized(body):
    fields(body, ['requestId', 'repositoryId', 'issueId', 'number', 'url', 'title', 'description'])
    identity(body['requestId'])
    integer(body['repositoryId'], 1, 2**53-1)
    integer(body['number'], 1, 2**53-1)
    node = text(body['issueId'], 256, True)
    if not re.fullmatch(r'[A-Za-z0-9_+/=-]+', node):
        raise RoadmapFault('Invalid GitHub issue identity.', 400)
    url = text(body['url'], 512, True)
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.netloc != 'github.com' or parts.query or parts.fragment
            or not re.fullmatch(r'/[A-Za-z0-9-]{1,39}/[A-Za-z0-9_.-]{1,100}/issues/' + str(body['number']), parts.path)
            or parts.path.split('/')[2] in ('.', '..')):
        raise RoadmapFault('Invalid GitHub issue link.', 400)
    text(body['title'], 240, True)
    text(body['description'])
    return body


def import_issue(db, project_id, body):
    body = normalized(body)
    request_id = body['requestId']
    fingerprint = hashlib.sha256(json.dumps(['github_issue', project_id, body['repositoryId'], body['issueId'], body['number']],
                                           separators=(',', ':')).encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        ensure(db)
        original = db.execute('SELECT request_hash,result FROM receipts WHERE request_id=?', (request_id,)).fetchone()
        if original:
            if original['request_hash'] != fingerprint:
                raise RoadmapFault('This request ID belongs to another issue.', 409)
            return json.loads(original['result'])
        previous = db.execute('''SELECT i.*,s.version_id FROM github_issue_origins i JOIN subversions s ON s.id=i.subversion_id
            WHERE i.repository_id=? AND i.issue_id=?''', (body['repositoryId'], body['issueId'])).fetchone()
        if previous:
            return {**binding(db), 'versionId': previous['version_id'], 'subversionId': previous['subversion_id'],
                    'githubIssue': public(previous)}
        if db.execute("SELECT 1 FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted')").fetchone():
            raise RoadmapFault('Reconcile the current roadmap workflow before adding an issue.', 409)
        if db.execute('SELECT count(*) FROM receipts').fetchone()[0] >= 50000:
            raise RoadmapFault('Roadmap receipt storage needs maintenance.', 503)
        now = timestamp()
        root = root_row(db)
        version = db.execute('SELECT * FROM versions WHERE id=?', (root['current_version_id'],)).fetchone()
        version_id = version['id']
        if version['status'] != 'open':
            minor = db.execute('SELECT max(minor) FROM versions WHERE major=?', (version['major'],)).fetchone()[0]
            version_id = create(db, {'kind': 'version'}, {'title': 'New', 'number': f'{version["major"]}.{minor+1}.X'}, now)['id']
            db.execute('UPDATE roadmap SET current_version_id=?', (version_id,))
        sub = create(db, {'kind': 'subversion', 'versionId': version_id},
                     {'title': body['title'], 'description': body['description'],
                      'notes': f'GitHub Issue #{body["number"]}\n{body["url"]}'}, now)['id']
        ref = {'versionId': version_id, 'subversionId': sub}
        create(db, {'kind': 'task', **ref}, {'description': f'Implement and verify GitHub issue #{body["number"]}.'}, now)
        acceptance = create(db, {'kind': 'acceptance', **ref},
                            {'description': f'Comment on GitHub issue #{body["number"]} with the result and close it as completed.'}, now)['id']
        db.execute('INSERT INTO github_issue_origins VALUES(?,?,?,?,?,?)', (
            body['repositoryId'], body['issueId'], body['number'], body['url'], sub, acceptance))
        db.execute('UPDATE roadmap SET revision=revision+1,updated_at=?', (now,))
        result = {**binding(db), 'versionId': version_id, 'subversionId': sub, 'githubIssue': origin(db, sub)}
        db.execute('INSERT INTO receipts VALUES(?,?,?,?,?)', (request_id, fingerprint, result['revision'], json.dumps(result), now))
        db.commit()
        return result
    except sqlite3.IntegrityError:
        raise RoadmapFault('The GitHub issue conflicts with its existing Roadmap entry.', 409) from None
    finally:
        db.rollback()
