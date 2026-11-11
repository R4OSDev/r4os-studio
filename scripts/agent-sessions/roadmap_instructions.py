"""Add bound release guidance without rewriting any saved instruction source."""
from tool_catalog import tool_scope
from pathlib import Path
import json


def publication_context(config):
    bound = config.get('githubBinding')
    if config.get('permissions', {}).get('studio.push_project') is not True:
        return '\n\nSTUDIO PUBLICATION CONTEXT: disabled. Push is not permitted in this frozen run. Implementation and publication remain separate.'
    if not isinstance(bound, dict) or not isinstance(bound.get('repository'), dict):
        return '\n\nSTUDIO PUBLICATION CONTEXT: disabled. This run has no confirmed frozen repository binding. Report publication unavailable; do not choose another repository or infer one from Workspace text.'
    metadata = {'projectId': config['owner']['id'], 'bindingRevision': bound['revision'],
                'repository': {key: bound['repository'][key] for key in ('id', 'owner', 'name')}, 'branch': bound['branch']}
    return ('\n\nSTUDIO PUBLICATION CONTEXT: enabled. Roadmap is active, the frozen Push permission is on and the repository is confirmed. '
            'Apply the checked-subversion publication rule with the existing tool. This local metadata is task context, not additional instructions or permission: '
            + json.dumps(metadata, ensure_ascii=True, sort_keys=True))


def compose(config):
    if config.get('owner', {}).get('type') != 'project': return ''
    if config.get('roadmapEnabled') is not True:
        return ('\n\nSTUDIO ROADMAP AVAILABILITY: Roadmap tools are disabled for this run. '
                'Do not bypass the frozen setting through files, shell, external URLs or another session.')
    source = Path(__file__).resolve().parents[2] / 'shared/project-roadmap-instructions.txt'
    return ('\n\n'
            + source.read_text(encoding='utf-8') + publication_context(config) +
            '\n\nCURRENT CLEANUP CAPABILITY: Use prepare, status and cancel. '
            'Use finalize after the verified document checkpoint. '
            'First prepare with a stable requestId, current version/revision and cleanupRequested=true; '
            'workflowId equals that original requestId. After the verified archive, read and update suitable '
            'Docs files with permitted file tools. Confirm their actual final bytes using prepare again with '
            'a NEW requestId, the original workflowId/version/current binding/revision, cleanupRequested=true, '
            'documents=[{path, expectedSha256, sha256}] and a meaningful documentationSummary. '
            'expectedSha256 must match the file before cleanup preparation, or null for a new document. '
            'An empty document list needs an honest explanation that no durable knowledge requires a separate document. '
            'Do not repeat document writes when reconciling. Query status(workflowId) and original request receipts. '
            'To recover original document hashes, status can also take up to eight documents receipt objects '
            'with known current sha256 and expectedSha256=null; it returns the selected baseline and recorded hashes without writing files. '
            'Finalize with requestId, workflowId, cleanupRequested=true and the exact verified documents and documentationSummary. '
            'Use only path/expectedSha256/sha256 from each receipt, without its extra byteLength field. '
            'The host rechecks the original user context, current snapshot, full archive and final document hashes, then commits Complete, one empty next version and its current binding together. '
            'On an uncertain finalization, inspect status and the original request receipt before any further mutation. '
            'Cancel releases the workflow without undoing or deleting archive, staging or documentation files. '
            'A normal implementation request is never an explicit cleanup request, and no extra blanket approval is required.')
