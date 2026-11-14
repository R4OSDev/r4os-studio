"""Durable, project-bound issue comment and close."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from common import ProjectFault, acquire, binding, document, folder, now, project as require_project, project_id, save, storage
from github import GitHub
from issue_origin import origin
from storage import connection
from validation import fields, identity, integer, text


ISSUE = '''query StudioIssueOutcome($owner:String!,$name:String!,$number:Int!){
  viewer{databaseId} repository(owner:$owner,name:$name){databaseId nameWithOwner hasIssuesEnabled
    issue(number:$number){id number url state stateReason viewerCanClose}
  }
}'''
ADD_COMMENT = '''mutation StudioIssueComment($issue:ID!,$body:String!,$reference:String!){
  addComment(input:{subjectId:$issue,body:$body,clientMutationId:$reference}){
    clientMutationId commentEdge{node{id url body author{login}}}
  }
}'''
CLOSE_ISSUE = '''mutation StudioIssueClose($issue:ID!,$reason:IssueClosedStateReason!,$reference:String!){
  closeIssue(input:{issueId:$issue,stateReason:$reason,clientMutationId:$reference}){
    clientMutationId issue{id url state stateReason}
  }
}'''
COMMENTS = '''query StudioOriginalIssueComment($issue:ID!,$after:String){
  node(id:$issue){__typename ... on Issue{id
    comments(first:50,after:$after){nodes{id url body author{login}} pageInfo{hasNextPage endCursor}}
  }}
}'''


def graphql(api, operation, query, variables):
    raw = api.request('/graphql', 'POST', {'operationName': operation, 'query': query, 'variables': variables})
    if not isinstance(raw, dict):
        raise ProjectFault('GitHub returned an invalid issue response.', 502)
    errors = raw.get('errors', [])
    if not isinstance(errors, list) or errors:
        data = raw.get('data')
        if operation in ('StudioIssueComment','StudioIssueClose') and isinstance(data,dict) and any(
                value is not None for value in data.values()):
            raise ProjectFault('GitHub returned a partial issue action response.',502)
        kinds = {str(error.get('type')) for error in errors if isinstance(error, dict)} if isinstance(errors, list) else set()
        if kinds.intersection({'FORBIDDEN', 'INSUFFICIENT_SCOPES', 'UNAUTHORIZED'}):
            raise ProjectFault('GitHub denied this issue action. Check Issues write permissions.', 403)
        if 'RATE_LIMITED' in kinds:
            raise ProjectFault('GitHub rate limited the issue operation. Check its original status before retrying.', 429)
        raise ProjectFault('GitHub did not confirm the issue action.', 502)
    if not isinstance(raw.get('data'), dict):
        raise ProjectFault('GitHub returned incomplete issue data.', 502)
    return raw['data']


def issue(api, bound, number, expected_issue=None):
    repo = bound['repository']
    value = graphql(api, 'StudioIssueOutcome', ISSUE, {'owner': repo['owner'], 'name': repo['name'], 'number': number})
    upstream, user = value.get('repository'), value.get('viewer') or {}
    if user.get('databaseId') != bound['userId'] or not upstream or upstream.get('databaseId') != repo['id']:
        raise ProjectFault('The GitHub account or repository changed.', 409)
    qualified = upstream.get('nameWithOwner')
    if not isinstance(qualified, str) or qualified.casefold() != (repo['owner'] + '/' + repo['name']).casefold() or upstream.get('hasIssuesEnabled') is not True:
        raise ProjectFault('GitHub Issues are unavailable for this repository.', 409)
    found = upstream.get('issue')
    if (not isinstance(found, dict) or found.get('number') != number or not isinstance(found.get('id'), str)
            or not re.fullmatch(r'[A-Za-z0-9_+/=-]{1,256}', found['id']) or (expected_issue and found['id'] != expected_issue)
            or found.get('url') != f'https://github.com/{qualified}/issues/{number}' or found.get('state') not in ('OPEN', 'CLOSED')
            or type(found.get('viewerCanClose')) is not bool):
        raise ProjectFault('The original GitHub issue could not be matched.', 409)
    return found


def comment_receipt(row, target, login, body):
    if not isinstance(row, dict) or row.get('body') != body or (row.get('author') or {}).get('login', '').casefold() != login.casefold():
        return None
    ident, url = row.get('id'), row.get('url')
    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_+/=-]{1,256}', ident):
        return None
    if not isinstance(url, str) or not re.fullmatch(re.escape(target['url']) + r'#issuecomment-[1-9][0-9]*', url):
        return None
    return {'id': ident, 'url': url}


def original_comment(api, target, body, guard):
    after = None
    for _ in range(40):
        guard()
        result = graphql(api, 'StudioOriginalIssueComment', COMMENTS, {'issue': target['id'], 'after': after}).get('node') or {}
        if result.get('__typename') != 'Issue' or result.get('id') != target['id']:
            raise ProjectFault('The original issue comment cannot be reconciled against this issue.', 409)
        page = result.get('comments') or {}
        for row in page.get('nodes', []):
            found = comment_receipt(row, target, api.user['login'], body)
            if found:
                return found
        info = page.get('pageInfo') or {}
        if info.get('hasNextPage') is False:
            return None
        cursor = info.get('endCursor')
        if not isinstance(cursor, str) or not cursor or len(cursor) > 2048 or cursor == after:
            break
        after = cursor
    return None


def match_binding(current, expected):
    return (current is not None and all(current[key] == expected[key] for key in ('revision','connectionId','userId','branch'))
            and all(current['repository'][key] == expected['repository'][key] for key in ('id','owner','name')))


def check_roadmap(projects, project, subversion_id, requested=None):
    with connection(projects, project) as db:
        source = origin(db, subversion_id) if db is not None else None
        if not source:
            raise ProjectFault('This subversion has no verified GitHub issue.', 404)
        sub = db.execute('SELECT status,version_id FROM subversions WHERE id=?', (subversion_id,)).fetchone()
        if requested and source != requested:
            raise ProjectFault('The linked issue or acceptance has changed.', 409)
        if sub['status'] not in ('open','complete'):
            raise ProjectFault('This Roadmap subversion is discarded.', 409)
        if db.execute("SELECT 1 FROM tasks WHERE subversion_id=? AND (status='open' OR status='discarded' AND trim(notes)='')",(subversion_id,)).fetchone() or db.execute(
                "SELECT 1 FROM acceptances WHERE subversion_id=? AND id!=? AND (status='open' OR status='discarded' AND trim(notes)='')", (subversion_id,source['acceptanceId'])).fetchone():
            raise ProjectFault('Finish the Roadmap tasks and other acceptance items before closing the issue.', 409)
        return source


def operation_path(projects, project, issue_id, repository_id):
    directory = Path(projects) / project_id(project) / '.studio/git/IssueActions'
    key = hashlib.sha256(f'{repository_id}:{issue_id}'.encode()).hexdigest()
    return directory/(key+'.json')


@contextmanager
def operation_lock(projects, project, target, repository_id):
    path = operation_path(projects, project, target['id'], repository_id)
    storage(projects, project)
    directory = path.parent
    directory.mkdir(mode=0o700, exist_ok=True)
    folder(directory)
    fd = os.open(path.with_suffix('.lock'), os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProjectFault('Invalid GitHub issue action lock.', 503)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ProjectFault('A GitHub action for this issue is already running. Check the original action.', 409) from None
        yield path
    finally:
        os.close(fd)


def public(receipt):
    return {key: receipt[key] for key in ('requestId','issueId','number','url','state','reason','comment','closedAt','subversionId','syncError','repositoryId') if key in receipt}


def refresh_notice(github, project, binding):
    directory = Path(github) / 'IssueRefresh'
    directory.mkdir(mode=0o700, exist_ok=True)
    path = folder(directory) / (project+'.json')
    fd = os.open(path.with_suffix('.json.lock'), os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        save(path, {'projectId':project,'bindingRevision':binding['revision'],
                 'repositoryId':binding['repository']['id'],'generation':str(uuid4())})
    finally:
        os.close(fd)


def record_roadmap(projects, project, receipt):
    subversion_id = receipt.get('subversionId')
    if not subversion_id:
        return
    with connection(projects, project) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            source = origin(db, subversion_id)
            if not source or source['issueId'] != receipt['issueId'] or source['repositoryId'] != receipt['repositoryId']:
                raise ProjectFault('The original Roadmap issue link changed; GitHub effects are recorded.', 409)
            if db.execute("SELECT 1 FROM workflows WHERE phase NOT IN ('complete','cancelled','aborted')").fetchone():
                raise ProjectFault('Reconcile the current Roadmap workflow before recording the GitHub result.', 409)
            status = 'done' if receipt['reason']=='COMPLETED' else 'discarded'
            previous = db.execute('SELECT status,notes FROM acceptances WHERE id=? AND subversion_id=?',
                                  (source['acceptanceId'],subversion_id)).fetchone()
            note = f'GitHub issue #{receipt["number"]} closed as {receipt["reason"]}. Comment: {receipt["comment"]["url"]}'
            if receipt['reason']=='NOT_PLANNED':
                note += '\nReason: ' + receipt['text']
            row = db.execute('SELECT status,notes FROM subversions WHERE id=?',(subversion_id,)).fetchone()
            if previous['status']==status and note in previous['notes'] and (status=='done' or row['status']=='discarded'):
                return
            if receipt['reason']=='NOT_PLANNED' and row['status']=='complete':
                raise ProjectFault('The linked Roadmap subversion is already complete.',409)
            stamp=now()
            notes=(previous['notes']+('\n' if previous['notes'] else '')+note)
            if len(notes.encode())>32768:
                raise ProjectFault('The acceptance notes are full. The GitHub result was retained for reconciliation.',409)
            db.execute('UPDATE acceptances SET status=?,notes=?,revision=revision+1,updated_at=? WHERE id=?',
                       (status,notes,stamp,source['acceptanceId']))
            from issue_origin import record_closure
            record_closure(db, subversion_id, receipt)
            if receipt['reason']=='NOT_PLANNED' and row['status']=='open':
                notes=(row['notes']+('\n' if row['notes'] else '')+note)
                if len(notes.encode())>32768:
                    raise ProjectFault('The subversion notes are full. The GitHub result was retained for reconciliation.',409)
                db.execute("UPDATE subversions SET status='discarded',notes=?,revision=revision+1,updated_at=? WHERE id=?",
                           (notes,stamp,subversion_id))
            db.execute('UPDATE roadmap SET revision=revision+1,updated_at=? WHERE singleton=1',(stamp,))
            db.commit()
        finally:
            db.rollback()


def execute(projects, github, project, payload, authorize, frozen=None, credential_revision=None):
    project_id(project)
    fields(payload, ['requestId','number','bindingRevision','credentialRevision','text','reason'], ['subversionId','issueId'])
    identity(payload['requestId'])
    number=integer(payload['number'],1); revision=integer(payload['bindingRevision'],1,2**53-1)
    token_revision=integer(payload['credentialRevision'],1,2**53-1)
    requested_reason=payload['reason']
    if requested_reason not in ('COMPLETED','NOT_PLANNED'):
        raise ProjectFault('Invalid GitHub issue outcome.',400)
    body=text(payload['text'],4000,True)
    sub=payload.get('subversionId')
    if sub: identity(sub)
    expected_issue=payload.get('issueId')
    if expected_issue is not None and (not isinstance(expected_issue,str) or not re.fullmatch(r'[A-Za-z0-9_+/=-]{1,256}',expected_issue)):
        raise ProjectFault('Invalid GitHub issue identity.',400)
    with acquire(projects,project):
        require_project(projects,project)
        bound=binding(projects,project)
        if not bound or bound['revision']!=revision or (frozen is not None and (not match_binding(bound,frozen) or token_revision!=credential_revision)):
            raise ProjectFault('The GitHub repository or connection changed.',409)
        authorize()
        api=GitHub(github,bound['connectionId'],token_revision,bound['userId'])
        def guard():
            authorize()
            if not match_binding(binding(projects,project),bound):
                raise ProjectFault('The GitHub repository binding changed.',409)
            api.assert_current()
        repo_id=bound['repository']['id']
        target=issue(api,bound,number,expected_issue)
        if sub and requested_reason=='COMPLETED':
            source=check_roadmap(projects,project,sub,None)
            if source['repositoryId']!=repo_id or source['issueId']!=target['id']:
                raise ProjectFault('The linked issue differs from the current repository.',409)
        elif requested_reason=='COMPLETED':
            raise ProjectFault('Select a linked Roadmap subversion.',400)
        else:
            with connection(projects,project) as db:
                if db is not None:
                    from issue_origin import linked
                    work=linked(db,repo_id,[number]).get(str(number))
                    if work and work['issueId']==target['id']:
                        sub=work['subversionId']
                        state=db.execute('SELECT status FROM subversions WHERE id=?',(sub,)).fetchone()['status']
                        if state=='complete':raise ProjectFault('The linked Roadmap subversion is already complete.',409)
        with operation_lock(projects,project,target,repo_id) as path:
            receipt=document(path) if path.exists() or path.is_symlink() else None
            if receipt:
                if (receipt['reason']!=requested_reason or (receipt['text']!=body and requested_reason=='NOT_PLANNED') or receipt.get('subversionId')!=sub
                        or receipt['issueId']!=target['id'] or receipt['repositoryId']!=repo_id):
                    raise ProjectFault('A different original GitHub issue action already exists.',409)
                if receipt['state']=='complete':
                    return public(receipt)
            else:
                if target['state']!='OPEN' or not target['viewerCanClose']:
                    raise ProjectFault('The issue is closed or this account cannot close it.',409 if target['state']!='OPEN' else 403)
                receipt={'requestId':payload['requestId'],'issueId':target['id'],'repositoryId':repo_id,'number':number,
                         'url':target['url'],'reason':requested_reason,'text':body,'subversionId':sub,'state':'ready'}
                save(path,receipt)
            reference=receipt['requestId']
            wire=receipt['text']+'\n\n<!-- studio-issue-action:'+reference+' -->'
            if receipt['state']=='ready':
                guard()
                if sub and requested_reason=='COMPLETED':check_roadmap(projects,project,sub,source)
                receipt['state']='comment_pending';save(path,receipt)
                try:
                    result=graphql(api,'StudioIssueComment',ADD_COMMENT,{'issue':target['id'],'body':wire,'reference':reference}).get('addComment') or {}
                    confirmed=comment_receipt((result.get('commentEdge') or {}).get('node'),target,api.user['login'],wire)
                    if result.get('clientMutationId')!=reference or not confirmed:
                        raise ProjectFault('The original GitHub comment is unconfirmed.',503)
                except ProjectFault as error:
                    if error.code in (400,401,403,404,422,429):
                        path.unlink()
                        raise
                    return {**public(receipt),'syncError':str(error)}
                receipt.update(state='commented',comment=confirmed);save(path,receipt)
            if receipt['state']=='comment_pending':
                try: confirmed=original_comment(api,target,wire,guard)
                except ProjectFault as error:
                    return {**public(receipt),'syncError':str(error)}
                if not confirmed:
                    return {**public(receipt),'syncError':'The original GitHub comment is unconfirmed. Check its status before any new action.'}
                receipt.update(state='commented',comment=confirmed);save(path,receipt)
            if receipt['state'] in ('commented','close_pending'):
                try:
                    guard()
                    value=issue(api,bound,number,target['id'])
                    if value['state']=='OPEN':
                        guard()
                        if sub and requested_reason=='COMPLETED':check_roadmap(projects,project,sub,source)
                        receipt['state']='close_pending';save(path,receipt)
                        result=graphql(api,'StudioIssueClose',CLOSE_ISSUE,
                            {'issue':target['id'],'reason':requested_reason,'reference':reference}).get('closeIssue') or {}
                        value=result.get('issue') or {}
                        if result.get('clientMutationId')!=reference or value.get('id')!=target['id'] or value.get('url')!=target['url']:
                            raise ProjectFault('The original GitHub close is unconfirmed.',503)
                    if value.get('state')!='CLOSED' or value.get('stateReason')!=requested_reason:
                        raise ProjectFault('GitHub reports a different closure state or reason. Check the original issue.',409)
                    receipt.update(state='closed',closedAt=now());save(path,receipt)
                except ProjectFault as error:
                    return {**public(receipt),'syncError':str(error)}
            if receipt['state']=='closed':
                try: refresh_notice(github,project,bound)
                except (ProjectFault,OSError): pass
                try: record_roadmap(projects,project,receipt)
                except (ProjectFault, OSError) as error:
                    return {**public(receipt),'syncError':str(error) if isinstance(error,ProjectFault) else 'Roadmap synchronization is unavailable.'}
                receipt['state']='complete';save(path,receipt)
            return public(receipt)
