"""Add bound release guidance without rewriting any saved instruction source."""
from pathlib import Path
from roadmap_access import availability


def compose(config):
    if config.get('owner', {}).get('type') != 'project': return ''
    if config.get('roadmapEnabled') is not True:
        return ('\n\nSTUDIO ROADMAP AVAILABILITY: Roadmap tools are disabled for this run. '
                'Earlier roadmap content remains in the native history but grants no access. '
                'Do not bypass the frozen setting through files, shell, external URLs or another session.')
    if not availability(config.get('engine', {}).get('profile'))['available']:
        return ('\n\nSTUDIO ROADMAP AVAILABILITY: The Roadmap preference is on, but this conversation '
                'keeps its original native tool profile without Roadmap tools. New session required. '
                'Its existing thread and history must be preserved. Do not claim access or bypass this '
                'capability with files, shell or an external roadmap service.')
    source = Path(__file__).resolve().parents[2] / 'shared/project-roadmap-instructions.txt'
    return ('\n\nThe following bound Roadmap contract applies to this run and supersedes conflicting '
            'earlier roadmap instructions. It changes no saved prompt source or tool permission.\n\n'
            + source.read_text(encoding='utf-8') +
            '\n\nCURRENT CLEANUP CAPABILITY: prepare, status and cancel are available in this release; '
            'finalize is not yet available. This overrides the earlier saved tool-description availability note. '
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
            'Cancel releases the workflow without undoing or deleting archive, staging or documentation files. '
            'A normal implementation request is never an explicit cleanup request, and no extra blanket approval is required.')
