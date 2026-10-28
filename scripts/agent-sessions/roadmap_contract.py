"""Precise v12 Roadmap declarations; saved v8-v11 declarations stay immutable."""
from roadmap_catalog import ID, REV, TEXT, obj


def choice(values):
    return {'type': 'string', 'enum': list(values)}


def union(variants):
    return {'oneOf': variants}


def target_schema(kind, entry=True):
    properties = {'kind': choice([kind])}
    if kind in ('subversion', 'task', 'acceptance'):
        properties['versionId'] = ID
    if kind in ('task', 'acceptance'):
        properties['subversionId'] = ID
    if entry:
        properties['id'] = ID
    return obj(properties, properties)


KINDS = ('roadmap', 'version', 'subversion', 'task', 'acceptance')
TARGET_DEFS = {('entry_' if entry else 'collection_') + kind: target_schema(kind, entry)
               for entry in (True, False) for kind in KINDS}


def reference(name):
    return {'$ref': '#/$defs/' + name}


def target(kind, entry=True):
    return reference(('entry_' if entry else 'collection_') + kind)


ENTRY = union([target(kind) for kind in KINDS])
PAGING = {'cursor': {'type': 'string', 'maxLength': 1024},
          'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}}
OFFSETS = {'offset': {'type': 'integer', 'minimum': 0, 'maximum': 100663296},
           'byteLimit': {'type': 'integer', 'minimum': 4, 'maximum': 8192}}
BINDING = {'operation': choice(['mutate']), 'requestId': ID,
           'expectedRevision': REV, 'currentVersionId': ID}


def read(views, properties=None, required=()):
    return obj({'view': choice(views), **(properties or {})}, ['view', *required])


READ_SCHEMA = {**union([
    read(['overview'], PAGING), read(['current', 'revision']),
    read(['versions'], PAGING),
    read(['subversions'], {**PAGING, 'versionId': ID}, ['versionId']),
    read(['tasks', 'acceptances'], {**PAGING, 'versionId': ID, 'subversionId': ID}, ['versionId', 'subversionId']),
    read(['entry'], {'target': ENTRY}, ['target']),
    *[read(['text'], {'target': union([target(kind) for kind in kinds]),
                     'field': choice([field]), **OFFSETS, 'expectedRevision': REV}, ['target', 'field'])
      for field, kinds in (('notes', KINDS), ('vision', ('version',)),
                           ('description', ('roadmap', 'subversion', 'task', 'acceptance')))],
    read(['receipt'], {'requestId': ID}, ['requestId']),
    read(['export_info'], {'exportId': ID}, ['exportId']),
    read(['export_chunk'], {'exportId': ID, **OFFSETS}, ['exportId']),
]), '$defs': TARGET_DEFS}


def content(kind, create=False):
    properties = {'notes': TEXT}
    if kind in ('version', 'subversion'):
        properties.update(number={'type': 'string', 'maxLength': 64},
                          title={'type': 'string', 'minLength': 1, 'maxLength': 240})
    if kind == 'version':
        properties['vision'] = TEXT
    else:
        properties['description'] = {**TEXT, **({'minLength': 1} if kind in ('task', 'acceptance') else {})}
    if kind != 'roadmap':
        properties['status'] = choice(['open', 'complete', 'discarded'] if kind in ('version', 'subversion')
                                      else ['open', 'done', 'discarded'])
    required = ['title' if kind in ('version', 'subversion') else 'description'] if create else []
    return {**obj(properties, required), 'minProperties': 1,
            'description': ('Task and acceptance text uses description; title is not supported.'
                            if kind in ('task', 'acceptance') else 'Only fields belonging to this entry type.')}


def partial(properties, required=()):
    # Constraints intersect the closed outer object; they allow its other fields.
    return {'properties': properties, **({'required': list(required)} if required else {})}


def kinds(values):
    return partial({'kind': choice(values)})


def group_target(values, entry):
    schema = target_schema(values[0], entry)
    schema['properties']['kind'] = choice(values)
    return schema


GROUPS = (('roadmap',), ('version',), ('subversion',), ('task', 'acceptance'))
CRUD = {**partial({'action': choice(['create', 'update'])}, ['input']), 'allOf': [union([
    partial({'target': kinds(group), 'input': content(group[0])}) for group in GROUPS
])]}
MUTATIONS_SCHEMA = union([
    CRUD,
    partial({'action': choice(['append_notes', 'replace_notes']), 'input': obj({'notes': TEXT}, ['notes'])}, ['input']),
    partial({'action': choice(['delete']), 'target': kinds(KINDS[1:]),
             'input': obj({'confirm': {'type': 'boolean', 'enum': [True]}}, ['confirm'])}, ['input']),
    partial({'action': choice(['reorder']), 'input': obj({'ids': {'type': 'array', 'maxItems': 500, 'items': ID}}, ['ids'])}, ['input']),
    partial({'action': choice(['set_current']), 'target': kinds(['version']), 'input': obj({})}),
])
TARGET_FORMS = union([
    partial({'action': choice(['create', 'reorder']), 'target': union([group_target(group, False) for group in GROUPS[1:]])}),
    partial({'action': choice(['update', 'append_notes', 'replace_notes', 'delete', 'set_current']),
             'target': union([group_target(group, True) for group in (('roadmap', 'version'), *GROUPS[2:])])}),
])

UPDATE_SCHEMA = {**union([
    obj({'operation': choice(['initialize']), 'requestId': ID}, ['operation', 'requestId']),
    obj({'operation': choice(['export']), 'requestId': ID, 'versionId': ID,
         'expectedRevision': REV, 'currentVersionId': ID},
        ['operation', 'requestId', 'versionId', 'expectedRevision', 'currentVersionId']),
    {**obj({**BINDING, 'action': {'type': 'string'}, 'target': {'type': 'object'}, 'input': {'type': 'object'}},
           [*BINDING, 'action', 'target']), 'allOf': [MUTATIONS_SCHEMA, TARGET_FORMS]},
])}

# Codex 0.163.0 compacts normalized schemas above 5,000 bytes. Factor field and
# target constraints instead of repeating a whole mutation per action/kind.
# Creation's conditional title/description requirement is stated in the model
# instructions and also checked by validate_arguments before any side effect.

DEFS = {
    'read_roadmap': (
        'Read this project’s shared internal roadmap. Send only the fields declared for the selected view. '
        'overview: optional cursor/limit; current/revision: view only. These reads return the latest revision; '
        'expectedRevision is allowed only for text. versions: optional cursor/limit; subversions: versionId; '
        'tasks/acceptances: versionId and subversionId; each collection accepts optional cursor/limit. '
        'entry: exact target with id and parent IDs. text: exact target, field, optional offset/byteLimit/expectedRevision; '
        'notes exists on every entry, vision only on versions, description on roadmap/subversion/task/acceptance. '
        'Previews are incomplete; use text pages and UTF-8 nextOffset for complete content. '
        'receipt(requestId) reconciles an original mutation; export_info/export_chunk require exportId. '
        'Read current before changes. No path or foreign project can be selected.', READ_SCHEMA),
    'update_roadmap': (
        'Change this project’s shared roadmap with exact operation-, action- and target-specific fields. '
        'initialize takes requestId only. mutate needs requestId, expectedRevision, currentVersionId, target and action. '
        'For create/update input: version uses title/number/vision/notes/status; subversion uses title/number/description/notes/status; '
        'task/acceptance uses description/notes/status and NEVER title; roadmap update uses description/notes. '
        'Create requires title for version/subversion, description for task/acceptance. Update supplies only changed fields. '
        'Task/acceptance status: open/done/discarded; version/subversion: open/complete/discarded. '
        'create/reorder targets omit id; other targets need id. Subversion needs versionId; task/acceptance also subversionId. '
        'append_notes/replace_notes take only input.notes. delete takes input.confirm=true. '
        'reorder takes input.ids containing the full ordered collection. set_current targets a version with no input or empty input. '
        'export needs requestId, versionId, expectedRevision and currentVersionId and prepares a complete immutable snapshot. '
        'Preserve notes and separate acceptance checks; record actual evidence before done. '
        'Use stable UUID request IDs and read receipt before an uncertain retry. No automatic cleanup or rollover.', UPDATE_SCHEMA),
}
