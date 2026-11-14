#!/usr/bin/env python3
"""Fixed input bridge between the Projects HTTP handler and the issue service."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project-git'))
from issue_outcome import execute, operation_path, public
from common import ProjectFault, acquire, binding, document, project as require_project
from github import connection_record
from validation import fields, identity, integer


def main(projects, github):
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384:
        raise ProjectFault('GitHub issue action is too large.', 413)
    request = json.loads(raw)
    fields(request, ['projectId', 'operation', 'input'])
    project, payload = identity(request['projectId']), request['input']
    if request['operation'] == 'discard':
        fields(payload,['requestId','number','bindingRevision','credentialRevision','text'],['issueId'])
        return execute(projects,github,project,{**payload,'reason':'NOT_PLANNED'},lambda:None)
    if request['operation'] != 'status':
        raise ProjectFault('Invalid GitHub issue action.',400)
    fields(payload,['number','bindingRevision','credentialRevision'],['issueId'])
    number = integer(payload['number'],1)
    revision = integer(payload['bindingRevision'],1,2**53-1)
    token_revision = integer(payload['credentialRevision'],1,2**53-1)
    with acquire(projects,project):
        require_project(projects,project)
        bound = binding(projects,project)
        if not bound or bound['revision'] != revision:
            raise ProjectFault('The GitHub repository changed.',409)
        identifier = payload.get('issueId')
        if identifier is None:
            return None
        if connection_record(github,bound['connectionId']).get('tokenRevision',1) != token_revision:
            raise ProjectFault('The GitHub token changed.',409)
        path = operation_path(projects,project,identifier,bound['repository']['id'])
        try:
            receipt = document(path)
        except FileNotFoundError:
            return None
        if receipt['reason'] != 'NOT_PLANNED' or receipt['number'] != number or receipt['issueId'] != identifier:
            return None
        return {**public(receipt),'text':receipt['text']}


if __name__=='__main__':
    os.umask(0o077)
    try:
        value=main(Path(sys.argv[1]),Path(sys.argv[2]))
        print(json.dumps({'result':value}))
    except ProjectFault as error:
        print(json.dumps({'error':str(error),'code':error.code}))
    except (OSError,ValueError,KeyError):
        print(json.dumps({'error':'The original GitHub issue outcome is unconfirmed. Check it before retrying.','code':503}))
