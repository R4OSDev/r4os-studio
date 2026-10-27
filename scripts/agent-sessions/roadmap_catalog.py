"""Additive v8 contracts, including stable cleanup phases before activation."""
def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


ID = {'type': 'string', 'minLength': 36, 'maxLength': 36}
REV = {'type': 'integer', 'minimum': 1, 'maximum': 9007199254740991}
TEXT = {'type': 'string', 'maxLength': 32768}
TARGET = obj({'kind': {'type': 'string', 'enum': ['roadmap', 'version', 'subversion', 'task', 'acceptance']},
              'id': ID, 'versionId': ID, 'subversionId': ID}, ['kind'])
CONTENT = obj({'number': {'type': 'string', 'maxLength': 64}, 'title': {'type': 'string', 'maxLength': 240},
               'description': TEXT, 'vision': TEXT, 'notes': TEXT,
               'status': {'type': 'string', 'enum': ['open', 'complete', 'done', 'discarded']},
               'confirm': {'type': 'boolean'}, 'ids': {'type': 'array', 'maxItems': 500, 'items': ID}})
DOCUMENT = obj({'path': {'type': 'string', 'maxLength': 1024},
                'sha256': {'type': 'string', 'minLength': 64, 'maxLength': 64},
                'expectedSha256': {'type': ['string', 'null'], 'maxLength': 64}}, ['path', 'sha256', 'expectedSha256'])

DEFS = {
    'read_roadmap': (
        'Read this project’s one shared internal roadmap, also used by every permitted project session and the WebApp. '
        'Read current version ID and revision before changes. view=overview/current/revision or paged versions/subversions/tasks/acceptances/entry. '
        'Collections and entry return text previews with byte counts; use view=text with target, field and byte offset for complete notes/vision/description. '
        'Never mistake a preview for a complete archive. Text and export_chunk return UTF-8-safe nextOffset; use returned revision to detect changes. '
        'view=receipt and requestId reconciles an original mutation/export without repeating it. export_info/export_chunk read an immutable prepared exportId. '
        'No project or host path can be selected. Missing roadmap requires explicit update initialize.',
        obj({'view': {'type': 'string', 'enum': ['overview', 'current', 'revision', 'versions', 'subversions', 'tasks', 'acceptances', 'entry', 'text', 'receipt', 'export_info', 'export_chunk']},
             'target': TARGET, 'versionId': ID, 'subversionId': ID,
             'cursor': {'type': 'string', 'maxLength': 1024}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
             'field': {'type': 'string', 'enum': ['notes', 'vision', 'description']},
             'offset': {'type': 'integer', 'minimum': 0, 'maximum': 100663296},
             'byteLimit': {'type': 'integer', 'minimum': 4, 'maximum': 8192},
             'expectedRevision': REV, 'requestId': ID, 'exportId': ID}, ['view'])),
    'update_roadmap': (
        'Change only this project’s shared internal roadmap through the same revision-protected logic as the WebApp. '
        'operation=initialize explicitly initializes a missing roadmap with requestId only. operation=mutate requires requestId, expectedRevision, currentVersionId, target and action; input is action-specific. '
        'Actions: create/update/append_notes/replace_notes/delete(confirm=true)/reorder(full ordered ids)/set_current. '
        'Subversion targets require versionId; tasks and acceptances also require subversionId. Task/acceptance status is open/done/discarded; version/subversion is open/complete/discarded. '
        'Preserve existing notes; append when adding findings. Keep acceptance checks separate and only mark actual work/checks done with evidence. '
        'operation=export prepares a complete immutable UTF-8 snapshot (versionId required) and returns its ID, revision, byteLength, filename and SHA-256; read export_chunk to retrieve all bytes. '
        'Use a stable UUID requestId, and reconcile view=receipt before any uncertain retry; identical input returns the original result. '
        'Ordinary edits and export never archive files, roll over a version or authorize cleanup.',
        obj({'operation': {'type': 'string', 'enum': ['initialize', 'mutate', 'export']}, 'requestId': ID,
             'expectedRevision': REV, 'currentVersionId': ID, 'versionId': ID, 'target': TARGET,
             'action': {'type': 'string', 'enum': ['create', 'update', 'append_notes', 'replace_notes', 'delete', 'reorder', 'set_current']},
             'input': CONTENT}, ['operation', 'requestId'])),
    'cleanup_roadmap': (
        'Explicit cleanup workflow for this project’s CURRENT main version. Trigger ONLY on a user request to "clean up the roadmap", "tidy up the roadmap" or "Roadmap aufräumen"; ordinary implementation is not cleanup. '
        'Stable phases: prepare(requestId, versionId, expectedRevision, currentVersionId, cleanupRequested=true), status(workflowId), '
        'finalize(requestId, workflowId, cleanupRequested=true, documents, documentationSummary), cancel(requestId, workflowId). '
        'Prepare must preserve the entire snapshot including every level of notes, IDs, ordering and discarded entries, write and verify Docs/Changelogs/<version>.txt without a V prefix, '
        'then let the agent extract durable information into appropriate Docs/* files using permitted file tools and preserving existing text. '
        'Final documents receipts contain path, expectedSha256 (null for a newly created file), final sha256 and a meaningful documentationSummary; never claim semantic completeness automatically. '
        'Only after archive/doc verification and resolution of open work may finalize mark the old version Complete and create exactly one next empty Open version titled New (0.1.X to 0.2.X). '
        'Keep history and project notes. Never overwrite a conflicting archive or repeat uncertain document writes. The explicit cleanup request authorizes the workflow without another blanket confirmation. '
        'Cleanup prepare/status/finalize/cancel are declared now but unavailable until the later workflow releases; do not emulate them with shell or ordinary status mutations.',
        obj({'action': {'type': 'string', 'enum': ['prepare', 'status', 'finalize', 'cancel']},
             'requestId': ID, 'workflowId': ID, 'versionId': ID, 'expectedRevision': REV, 'currentVersionId': ID,
             'cleanupRequested': {'type': 'boolean'}, 'documents': {'type': 'array', 'maxItems': 32, 'items': DOCUMENT},
             'documentationSummary': {'type': 'string', 'maxLength': 8192}}, ['action'])),
}
