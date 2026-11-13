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
    return ('\n\nSTUDIO PUBLICATION CONTEXT: enabled. Commit and push each finished subversion after all required '
            'checks have passed. Use a reviewed selection and a commitMessage with the subversion number. '
            'Check the original job/request ID after an uncertain reply. A confirmed nothingToPush completes publication. '
            'Bound repository data follows. ' + json.dumps(metadata, ensure_ascii=True, separators=(',', ':')))


def compose(config):
    if config.get('owner', {}).get('type') != 'project': return ''
    if config.get('roadmapEnabled') is not True:
        return ('\n\nSTUDIO ROADMAP AVAILABILITY: Roadmap tools are disabled for this run. '
                'Do not bypass the frozen setting through files, shell, external URLs or another session.')
    source = Path(__file__).resolve().parents[2] / 'shared/project-roadmap-instructions.txt'
    text = source.read_text(encoding='utf-8')
    presentation = config.get('toolCatalog', {}).get('presentation')
    if presentation == 'standard_initialize':
        text = text.replace('Enable Roadmap administration for initialization, import, export or cleanup.',
                            'If the roadmap read returns nextCall, use it to initialize before writing. '
                            'Enable Roadmap administration for import, export or cleanup.')
    guidance = '\n\n' + text + publication_context(config)
    if presentation in ('standard', 'standard_initialize'): return guidance
    return (guidance+'\n\nCURRENT CLEANUP CAPABILITY: Prepare the selected version and verify the complete archive in '
            'Docs/Changelogs/<version>.txt. Update the relevant Docs with permitted file tools. Use prepare again '
            'with a new requestId, the same workflowId, documents and documentationSummary. For each document, '
            'expectedSha256 is its starting hash or null for a new file. sha256 is its final hash. '
            'Explain an empty document list in the summary. Finalize using the verified receipt to complete the version '
            'and create one next version. Use status and the original receipt to reconcile a lost reply.')
