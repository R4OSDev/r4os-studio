"""Fixed SDK approval of a prepared pull; no repository scripts or source publication."""
import json
import os
from pathlib import Path
import sys
from store import ProjectFault
from project_use import project_id
from project_maintenance import project
from github_import import files, checked_profile, manifest
from git_metadata import portable


def main():
    os.umask(0o077)
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192: raise ProjectFault('Pull validation is too large.', 400)
    request = json.loads(raw)
    if set(request) != {'id', 'requestId', 'operation'} or request['operation'] != 'validate': raise ProjectFault('Invalid pull validation.', 400)
    identity, ident = project_id(request['id']), project_id(request['requestId'])
    projects, root = Path(sys.argv[1]).absolute(), Path(sys.argv[2]).resolve()
    job = files.document(projects / '.studio/github/Jobs' / ident / 'job.json')
    if job['projectId'] != identity or job['kind'] != 'prepare_pull' or job['state'] != 'completed': raise ProjectFault('Wait for the original pull preparation.', 409)
    stage = files.folder(projects / identity / '.studio/git/Pulls' / ident)
    prepared = files.document(stage / 'prepare.json'); source = files.folder(stage / 'New')
    if prepared['projectId'] != identity or prepared['requestId'] != ident or files.digest(files.inventory(source)) != prepared['newSnapshot']: raise ProjectFault('The prepared source identity changed.', 409)
    current = project(projects, identity); metadata = portable(current)
    if (source / '.r4os-studio/project.json').exists() and files.document(source / '.r4os-studio/project.json', 65536) != metadata:
        raise ProjectFault('Incoming portable pins differ from this project. Use a separate import for another component profile.', 409)
    context, language, template = checked_profile(root, projects, metadata, None)
    manifest(context, source, language, template, current['moduleName'])
    if files.digest(files.inventory(source)) != prepared['newSnapshot']: raise ProjectFault('Prepared sources changed during SDK validation.', 409)
    files.save(stage / 'approval.json', {'schema': 1, 'approved': True, 'projectId': identity, 'requestId': ident, 'newHead': prepared['newHead'], 'newSnapshot': prepared['newSnapshot'], 'projectRevision': current['revision'], 'pinsHash': files.digest(current['pins']), 'checkedAt': files.now()})
    print(json.dumps({'result': {'validated': True, 'commit': prepared['newHead']}}))


if __name__ == '__main__':
    try: main()
    except ProjectFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'The SDK could not approve the prepared pull. Current project sources were preserved.', 'code': 503})); sys.exit(1)
