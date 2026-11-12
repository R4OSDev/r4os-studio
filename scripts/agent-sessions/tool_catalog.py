"""The installed Studio tool catalog, selected by workspace kind, never session age."""
from copy import deepcopy
from functools import lru_cache
import json
import hashlib
from pathlib import Path

GOAL_TOOLS = ('get_goal', 'update_goal')
WEB_TOOLS = ('web_search',)
ROOT = Path(__file__).resolve().parents[2]


def tool_scope(value='project'):
    if isinstance(value,dict):
        owner=value.get('owner') or {}
        if owner.get('type') in ('project','skill'):return owner['type']
        value=value.get('toolScope') or value.get('engine',{}).get('toolScope') or value.get('profile') or value.get('engine',{}).get('profile') or 'project'
    # Historical names are read only to identify workspace kind. Their version
    # does not select capabilities or restrict the next run.
    if value=='skill' or isinstance(value,str) and value.startswith('studio-skill-tools-v'):return 'skill'
    if value in (None,'project') or isinstance(value,str) and value.startswith('studio-tools-v'):return 'project'
    raise ValueError('Unknown Studio workspace kind.')


@lru_cache(maxsize=16)
def catalog(root=ROOT):
    value=json.loads((root/'shared/agent-tools.json').read_text())
    if set(value)!={'project','skill'}:raise ValueError('The installed tool catalog is invalid.')
    for declarations in value.values():
        names=[item['name'] for item in declarations]
        if len(names)!=len(set(names)) or any(not name.startswith('studio_') for name in names):
            raise ValueError('The installed tool catalog contains invalid names.')
    return value


@lru_cache(maxsize=32)
def prepared(scope, root=ROOT, presentation='standard', file_writes=None, run_timeout=None, result_ids=None):
    tools = {}
    for original in tool_definitions(scope, root, file_writes, run_timeout, result_ids).values():
        if presentation == 'legacy' and original.get('dispatch') or presentation != 'legacy' and original.get('retired'):
            continue
        tool = deepcopy(original)
        tool.pop('dispatch',None);tool.pop('retired',None)
        wire = tool.pop('modelSchemas', {})
        if presentation in wire:
            tool['inputSchema'] = wire[presentation]
        if file_writes and original['name'] in ('studio_write_workspace','studio_write_file','studio_apply_patch'):
            schema = tool['inputSchema']
            for variant in schema.get('oneOf', [schema]):
                for field in ('expectedSha256', 'expectedHashes'):
                    if field not in variant.get('required', []):
                        variant.get('properties', {}).pop(field, None)
        expand(tool['inputSchema'])
        tools[tool['name']]=tool
    return tools


def expand(schema):
    schema.setdefault('type','object')
    variants = schema.get('oneOf',[])
    # Keep precise variants and expose their common envelope to model grammars.
    if 'properties' in schema or not variants or any(
            part.get('type')!='object' or part.get('additionalProperties') is not False for part in variants): return
    fields = {}
    for part in variants:
        for name, rule in part.get('properties',{}).items():
            if rule not in fields.setdefault(name,[]): fields[name].append(rule)
    properties = {}
    for name,rules in fields.items():
        if len(rules)==1: properties[name]=rules[0]
        elif all('enum' in rule and set(rule)<={'type','enum','description'}
                 and rule.get('type')==rules[0].get('type') for rule in rules):
            values=list(dict.fromkeys(value for rule in rules for value in rule['enum']))
            properties[name]={'type':rules[0]['type'],'enum':values}
        else: properties[name]={'anyOf':rules}
    schema['properties']=properties
    schema['required']=[name for name in variants[0].get('required',[])
                        if all(name in part.get('required',[]) for part in variants)]


def restricted(tool, actions):
    if not actions: raise ValueError('The accepted tool has no available actions.')
    schema = {key:value for key,value in tool['inputSchema'].items() if key not in ('oneOf','properties','required')}
    schema['oneOf'] = [part for part in tool['inputSchema']['oneOf']
                       if any(action in actions for action in part['properties']['action']['enum'])]
    expand(schema)
    if set(schema['properties']['action']['enum']) != set(actions):
        raise ValueError('The accepted tool actions are unavailable.')
    # The broker keeps the exact variants. The model needs their shared fields
    # and the actions admitted for this run only.
    del schema['oneOf']
    schema['additionalProperties']=False
    return {**tool,'inputSchema':schema}


VARIANT_SELECTORS = ('operation', 'view', 'action', 'kind', 'scope', 'mode', 'field')


def argument_requirements(tools, scope, root, version, file_writes=None, run_timeout=None, result_ids=None):
    """Show broker-required variants in the flat declaration used by adapters."""
    if version is None:
        return tools
    if type(version) is not int or version != 1:
        raise ValueError('The original tool argument requirements are unavailable.')
    definitions = tool_definitions(scope, root, file_writes, run_timeout, result_ids)
    decorated = []
    for tool in tools:
        canonical = definitions[tool['name'][7:]]['inputSchema']
        schema = tool['inputSchema']
        properties = dict(schema.get('properties', {}))
        common = set(schema.get('required', []))
        patterns = []
        for variant in canonical.get('oneOf', []):
            fields = variant.get('properties', {})
            selectors = {}
            for field in VARIANT_SELECTORS:
                values = fields.get(field, {}).get('enum')
                if values:
                    available = properties.get(field, {}).get('enum', values)
                    selectors[field] = [value for value in values if value in available]
            if any(not values for values in selectors.values()):
                continue
            required = [field for field in variant.get('required', []) if field not in common]
            if not required:
                continue
            for field in required:
                if field not in properties:
                    properties[field] = fields[field]
            parts = [field + '=' + '/'.join(str(value) for value in values) for field, values in selectors.items()]
            parts.extend(field for field in required if field not in selectors)
            patterns.append('{' + ', '.join(parts) + '}')
        if patterns:
            hint = ' Required field sets by variant include ' + ' or '.join(dict.fromkeys(patterns)) + '.'
            tool = {**tool, 'description': tool.get('description', '') + hint,
                    'inputSchema': {**schema, 'properties': properties}}
        if tool['name'] == 'studio_send_vm_input':
            # Execution accepts a different exact field set for each input
            # kind. The broker schema also accepts legacy console/GUI forms.
            tool = {**tool, 'description': tool['description'] +
                    ' For text provide text. For guiText provide frameId and text. For key provide frameId and key. '
                    'For click provide frameId, x and y. For gesture or keyPlan provide frameId and steps.'}
        decorated.append(tool)
    return decorated


def digest(tools):
    raw = json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode()
    return hashlib.sha256(raw).hexdigest()


def declarations(scope='project', root=ROOT):
    """Read-only, in catalogue or original request order."""
    kind = tool_scope(scope)
    saved=scope.get('toolCatalog') if isinstance(scope,dict) else None
    presentation = saved.get('presentation','legacy') if isinstance(saved,dict) else 'standard'
    file_writes = saved.get('fileWritePreconditions') if isinstance(saved,dict) else None
    run_timeout = saved.get('runTestTimeoutSeconds') if isinstance(saved,dict) else None
    result_ids = saved.get('resultIds') if isinstance(saved,dict) else None
    by_name = prepared(kind, root, presentation, file_writes, run_timeout, result_ids)
    if saved is not None:
        if (not isinstance(saved,dict) or saved.get('scope')!=kind or saved.get('version',1) not in (1,2)
                or not isinstance(saved.get('tools'),list) or any(not isinstance(name,str) for name in saved['tools'])
                or len(set(saved['tools']))!=len(saved['tools'])):
            raise ValueError('The original tool catalog binding is invalid.')
        if any(name not in by_name for name in saved['tools']):raise ValueError('The original accepted tool catalog is unavailable.')
        actions=saved.get('actions',{})
        if not isinstance(actions,dict) or not actions.keys()<=set(saved['tools']):
            raise ValueError('The original tool action binding is invalid.')
        tools=[restricted(by_name[name],actions[name]) if name in actions else by_name[name] for name in saved['tools']]
        tools=argument_requirements(tools,kind,root,saved.get('argumentRequirements'),file_writes,run_timeout,result_ids)
        if digest(tools)!=saved.get('sha256'):
            raise ValueError('The original tool definitions changed. Preserve the original input; no new permissions were granted.')
        return tools
    return list(by_name.values())


def specifications(scope='project'):
    return deepcopy(declarations(scope))


def native_specifications(scope='project'):
    return [t for t in specifications(scope) if t['name'] != 'studio_generate_image' and t['name'][7:] not in ((*WEB_TOOLS,) if isinstance(scope,dict) and scope.get('goalKeepalive') else (*GOAL_TOOLS,*WEB_TOOLS))]


def tools_for(scope='project'):
    return tuple(item['name'][7:] for item in catalog()[tool_scope(scope)])


def permission_tools(scope='project'):
    grouped={'read_roadmap','update_roadmap','cleanup_roadmap','read_environment_notes','record_environment_note',*GOAL_TOOLS,*WEB_TOOLS}
    return tuple(name for name,item in tool_definitions(tool_scope(scope)).items() if name not in grouped and not item.get('dispatch'))


def automatic_file_writes(config):
    return (config.get('toolCatalog') or {}).get('fileWritePreconditions') == 1


@lru_cache(maxsize=16)
def execution_timeout(root=ROOT):
    return json.loads((root/'shared/development-host.json').read_text())['limits']['executionTimeoutSeconds']


@lru_cache(maxsize=32)
def tool_definitions(scope,root=ROOT,file_writes=None,run_timeout=None,result_ids=None):
    tools = {item['name'][7:]: item for item in catalog(root)[scope]}
    if result_ids is not None:
        if type(result_ids) is not int or result_ids != 1:
            raise ValueError('The original result ID contract is unavailable.')
        for name, selector, views in (('read_result','action',('context','image')),
                                      ('read_context_result','view',('result','image'))):
            tool = deepcopy(tools[name])
            for variant in tool['inputSchema']['oneOf']:
                fields = variant['properties']
                if fields[selector]['enum'][0] in views:
                    del fields['reference']
                    fields['resultId'] = {'type':'string','minLength':16,'maxLength':16,
                                          'description':'The resultId returned in the saved preview or checkpoint index.'}
                    variant['required'] = ['resultId' if field == 'reference' else field for field in variant['required']]
            tool['description'] = ('Read a saved result or original image by resultId. Use the returned UTF-8 offset for pages. '
                                   'Read a checkpoint index with its checkpointId and sha256.')
            if name == 'read_result':
                tool['description'] += ' For a skill result, use its original skill reference.'
            tools[name] = tool
    # Original catalogs still reproduce their declared override range exactly.
    if run_timeout is not None:
        if scope != 'project' or type(run_timeout) is not int or not 1 <= run_timeout <= execution_timeout(root):
            raise ValueError('The original Run & Test timeout contract is unavailable.')
        run = deepcopy(tools['run_project'])
        run['inputSchema']['properties']['timeoutSeconds']['maximum'] = run_timeout
        run['description'] += (f' Uses the project Run & Test limit ({run_timeout} seconds by default) unless timeoutSeconds is supplied. '
                               'Deploy again if the guest helper cannot run for the chosen duration.')
        tools['run_project'] = run
    if file_writes is None:
        return tools
    if type(file_writes) is not int or file_writes != 1:
        raise ValueError('The original file write contract is unavailable.')
    for name, field in (('write_file','expectedSha256'), ('apply_patch','expectedHashes')):
        tool = deepcopy(tools[name])
        tool['inputSchema']['required'].remove(field)
        tools[name] = tool
    tools['write_file']['description'] = 'Replace an existing UTF-8 file using the file version previously returned by Studio.'
    tools['apply_patch']['description'] = (
        'Apply a Codex-format patch using the versions of existing files previously returned by Studio. '
        'Read each existing source file before editing. New paths must be free.')
    combined = deepcopy(tools['write_workspace'])
    write = next(variant for variant in combined['inputSchema']['oneOf']
                 if variant['properties']['action']['enum'] == ['write_file'])
    write['required'].remove('expectedSha256')
    create = deepcopy(write)
    create['properties']['action']['enum'] = ['create_file']
    del create['properties']['expectedSha256']
    combined['inputSchema']['oneOf'].insert(1, create)
    combined['dispatch']['create_file'] = {'tool':'write_file','set':{'expectedSha256':None}}
    combined['description'] = (
        'Write a previously read UTF-8 file with write_file. Create a new file with create_file or a directory with create_directory.')
    tools['write_workspace'] = combined
    return tools


def operation(name,value,scope='project'):
    selected = scope.get('toolCatalog', {}) if isinstance(scope,dict) else {}
    action=tool_definitions(tool_scope(scope),file_writes=selected.get('fileWritePreconditions'))[name].get('dispatch')
    if not action: return name,value
    entry=action[value['action']]
    return entry['tool'],{**{key:v for key,v in value.items() if key!='action'},**entry.get('set',{})}


def result_readback(config, action):
    selected=config.get('toolCatalog',{})
    if action in selected.get('actions',{}).get('studio_read_result',()):
        return {'tool':'studio_read_result','action':action}
    if action=='skill':
        if selected.get('version')==2 and 'studio_read_skill_result' not in selected['tools']: return {}
        return {'tool':'studio_read_skill_result'}
    return {'tool':'studio_read_context_result','view':'result' if action=='context' else action}


def validate_arguments(name,value,scope='project'):
    if name in ('deploy_project','run_project') and isinstance(value,dict) and any(key in value for key in ('desktopShortcut','desktopLink')):
        raise ValueError('Use the declared deploy or run arguments. For an explicitly requested guest shortcut, use the project VM SSH tool when permitted.')
    if name=='write_file' and isinstance(value,dict) and 'expectedSha256' in value:
        from file_worker import validate_expected,Fault
        try:validate_expected(value['expectedSha256'])
        except Fault as error:raise ValueError('arguments.expectedSha256: '+str(error)) from None
    selected = scope.get('toolCatalog',{}) if isinstance(scope,dict) else {}
    definition = tool_definitions(tool_scope(scope),file_writes=selected.get('fileWritePreconditions'),
                                  run_timeout=selected.get('runTestTimeoutSeconds'),result_ids=selected.get('resultIds')).get(name)
    if definition is None:raise ValueError('This tool is unavailable for this workspace kind.')
    root = definition['inputSchema']
    actions = selected.get('actions',{}).get('studio_'+name)
    if actions is not None and isinstance(value,dict) and value.get('action') not in actions:
        raise ValueError('arguments.action: allowed values are '+', '.join(actions)+'.')
    wire = definition.get('modelSchemas',{}).get(selected.get('presentation'))
    if wire and isinstance(value,dict):
        if name=='send_vm_input' and value.get('kind')=='text' and 'frameId' in value:
            raise ValueError('arguments.kind: use guiText for text bound to a GUI frame.')
        for field in ('operation','view'):
            allowed = wire.get('properties',{}).get(field,{}).get('enum')
            if allowed and field in value and value[field] not in allowed:
                raise ValueError('arguments.'+field+': allowed values are '+', '.join(allowed)+'.')

    def resolve(rule):
        if '$ref' not in rule: return rule
        key = rule['$ref'].removeprefix('#/$defs/')
        return root['$defs'][key]

    def selects(rule, v):
        rule = resolve(rule)
        if not isinstance(v, dict): return True
        properties = rule.get('properties', {})
        for key in ('operation', 'view', 'action', 'kind', 'field'):
            if key in v and 'enum' in properties.get(key, {}) and v[key] not in properties[key]['enum']:
                return False
        if 'target' in v and 'target' in properties and not selects(properties['target'], v['target']): return False
        if 'oneOf' in rule and not any(selects(candidate, v) for candidate in rule['oneOf']): return False
        return all(selects(candidate, v) for candidate in rule.get('allOf', []))

    def validate(rule, v, path='arguments'):
        rule = resolve(rule)
        for candidate in rule.get('allOf', []): validate(candidate, v, path)
        if 'oneOf' in rule:
            matched = 0; failures = []
            for candidate in rule['oneOf']:
                try: validate(candidate, v, path); matched += 1
                except ValueError as error: failures.append((candidate, str(error)))
            if matched != 1:
                selected = [candidate for candidate in rule['oneOf'] if selects(candidate, v)]
                if matched == 0 and len(selected) == 1:
                    validate(selected[0], v, path)
                if matched == 0:
                    possible = selected or rule['oneOf']
                    if isinstance(v, dict) and possible:
                        required = [set(resolve(candidate).get('required', [])) for candidate in possible]
                        missing = sorted(set.intersection(*required) - v.keys())
                        if missing:
                            hints = []
                            for key in missing[:2]:
                                values = []
                                for candidate in possible:
                                    for value in resolve(candidate).get('properties', {}).get(key, {}).get('enum', []):
                                        if value not in values: values.append(value)
                                if values: hints.append(key + ' allowed values: ' + ', '.join(str(value)[:64] for value in values[:12]))
                            detail = '; '.join(['missing fields: ' + ', '.join(missing[:8]), *hints])
                            raise ValueError(path + ': ' + detail)
                    errors = list(dict.fromkeys(error for candidate, error in failures if candidate in possible))
                    detail = ' | '.join(error[:280] for error in errors[:3])
                    raise ValueError(path + ': no declared variant matches; possible variant errors: ' + detail)
                raise ValueError(path + ': select exactly one declared operation, view and target with its required fields.')
        if not any(key in rule for key in ('type', 'properties', 'required')): return
        types = rule.get('type', 'object') if isinstance(rule.get('type'), list) else [rule.get('type', 'object')]
        actual = 'null' if v is None else ('boolean' if type(v) is bool else ('integer' if type(v) is int else ('string' if isinstance(v, str) else ('object' if isinstance(v, dict) else ('array' if isinstance(v, list) else 'invalid')))))
        if actual not in types: raise ValueError(path + ': expected ' + '/'.join(types) + '.')
        if 'enum' in rule and v not in rule['enum']:
            raise ValueError(path + ': allowed values are ' + ', '.join(str(item) for item in rule['enum']) + '.')
        if actual == 'string':
            if '\x00' in v or not rule.get('minLength', 0) <= len(v.encode()) <= rule.get('maxLength', 8192): raise ValueError(path + ': text exceeds its limit or is empty.')
        if actual == 'integer' and not rule.get('minimum', 0) <= v <= rule.get('maximum', 1000000): raise ValueError(path + ': number is outside its allowed range.')
        if actual == 'array':
            if len(v) > rule.get('maxItems', 8): raise ValueError(path + ': too many entries.')
            for entry in v: validate(rule['items'], entry, path + '[]')
        if actual == 'object':
            if len(v) > 64: raise ValueError(path + ': too many fields.')
            missing = sorted(set(rule.get('required', [])) - v.keys())
            unexpected = [key for key in v if key not in rule.get('properties', {}) and rule.get('additionalProperties') is False]
            if missing or unexpected:
                details = []
                if missing: details.append('missing fields: ' + ', '.join(missing))
                if unexpected: details.append('unexpected fields: ' + ', '.join(repr(key[:80]) for key in unexpected[:8]))
                details.append('allowed fields: ' + ', '.join(rule.get('properties', {})))
                if rule.get('description'): details.append(rule['description'])
                raise ValueError(path + ': ' + '; '.join(details))
            if len(v) < rule.get('minProperties', 0): raise ValueError(path + ': supply at least one field to change.')
            for key, entry in v.items():
                spec = rule.get('properties', {}).get(key, rule.get('additionalProperties', True))
                if spec is True: continue
                if not isinstance(spec, dict): raise ValueError('Unknown tool argument.')
                validate(spec, entry, path + '.' + key)
    validate(root, value)
    if definition.get('dispatch'):
        handler, arguments = operation(name,value,scope)
        validate_arguments(handler,arguments,scope)
    if (name == 'update_roadmap'
            and value.get('operation') == 'mutate' and value.get('action') == 'create'):
        kind = value['target']['kind']
        required = 'title' if kind in ('version', 'subversion') else 'description'
        if required not in value['input']:
            raise ValueError('arguments.input: ' + kind + ' create requires ' + required + '.')


def native_capabilities():
    """Permission capabilities, deliberately not callable tool declarations."""
    return [{'id':'web_search','defaultEnabled':True},{'id':'image_generation','defaultEnabled':True}]
