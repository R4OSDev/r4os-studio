"""Operation-specific Roadmap declarations for new runs."""

from copy import deepcopy

EDIT_PRESENTATIONS = ('standard_edit', 'administration_edit')
EDIT_OPERATIONS = ('mutate', 'batch')
BINDING_FIELDS = ('expectedRevision', 'currentVersionId')


def edit_schema(schemas, administration):
    base = deepcopy(schemas['administration' if administration else 'standard'])
    fields = base['properties']
    required = {
        'initialize': ('requestId',),
        'mutate': ('requestId', 'action', 'target'),
        'batch': ('requestId', 'operations'),
    }
    optional = {'mutate': ('input',), 'import_preview': ('numberPolicy',)}
    if administration:
        binding = ('requestId', 'expectedRevision', 'currentVersionId')
        required.update(export=(*binding, 'versionId'),
                        import_preview=(*binding, 'mode', 'target', 'source'),
                        import_apply=(*binding, 'previewId', 'previewSha256', 'confirm'))
    variants = []
    for operation, names in required.items():
        variants.append({
            'type': 'object',
            'properties': {'operation': {'type': 'string', 'enum': [operation]},
                           **{name: fields[name] for name in (*names, *optional.get(operation, ()))}},
            'required': ['operation', *names],
            'additionalProperties': False,
        })
    allowed = {name for variant in variants for name in variant['properties']}
    return {**base, 'properties': {name: spec if name != 'operation' else {**spec, 'enum': list(required)}
                                  for name, spec in fields.items() if name in allowed},
            'required': ['operation', 'requestId'], 'oneOf': variants}


def description(administration):
    text = ('Edit this project’s roadmap. Read current or overview first. Follow nextCall to initialize a missing roadmap. '
            'Studio uses the revision and current version from the latest returned read or write. '
            'initialize requires requestId. mutate requires requestId, action and target, plus input for a change. '
            'batch requires requestId and operations. Use exact target and parent IDs or earlier $key references in the same batch. '
            'Use vision for a main version and description for subversions, tasks and acceptances. '
            'Use the same requestId for the original operation and read its receipt after an uncertain reply.')
    if administration:
        text += ' Export and import use the explicit revision and currentVersionId from the matching read.'
    return text


def validate_edit(value):
    operation = value.get('operation')
    if operation not in EDIT_OPERATIONS:
        return
    fields = ('requestId', 'action', 'target') if operation == 'mutate' else ('requestId', 'operations')
    missing = [name for name in fields if name not in value]
    if missing:
        raise ValueError(f'Roadmap {operation} requires ' + ', '.join(missing) + '.')
    if operation == 'batch' and value['operations'] == []:
        raise ValueError('Roadmap batch requires at least one operation.')
    if sum(field in value for field in BINDING_FIELDS) == 1:
        raise ValueError('Roadmap revision and currentVersionId must be supplied together. Studio can use the latest Roadmap read.')
    if operation == 'mutate' and value['action'] == 'create' and value['target'] == {'kind': 'roadmap'}:
        raise ValueError('Use operation=initialize with requestId to create a missing roadmap.')
    if operation == 'batch' and isinstance(value['operations'], list):
        for index, change in enumerate(value['operations']):
            if (isinstance(change, dict) and change.get('action') == 'create'
                    and change.get('target') == {'kind': 'roadmap'}):
                raise ValueError(f'Roadmap batch operations[{index}]: use initialize to create a missing roadmap.')


def optional_binding(schema):
    return {**schema, 'oneOf': [
        {**variant, 'required': [name for name in variant['required'] if name not in BINDING_FIELDS]}
        if variant['properties']['operation']['enum'][0] in EDIT_OPERATIONS else variant
        for variant in schema['oneOf']
    ]}
