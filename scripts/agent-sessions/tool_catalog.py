"""The installed Studio tool catalog, selected by workspace kind, never session age."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

GOAL_TOOLS = ('get_goal', 'update_goal')
WEB_TOOLS = ('web_search',)


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


@lru_cache(maxsize=1)
def catalog():
    value=json.loads((Path(__file__).resolve().parents[2]/'shared/agent-tools.json').read_text())
    if set(value)!={'project','skill'}:raise ValueError('The installed tool catalog is invalid.')
    for declarations in value.values():
        names=[item['name'] for item in declarations]
        if len(names)!=len(set(names)) or any(not name.startswith('studio_') for name in names):
            raise ValueError('The installed tool catalog contains invalid names.')
    return value


def specifications(scope='project'):
    tools = deepcopy(catalog()[tool_scope(scope)])
    for tool in tools:
        schema = tool['inputSchema']
        schema.setdefault('type', 'object')
        variants = schema.get('oneOf', [])
        # Expose object fields to model grammars while retaining every original
        # variant. The broker still validates against the unmodified catalog.
        if 'properties' in schema or not variants or any(
                part.get('type') != 'object' or part.get('additionalProperties') is not False for part in variants):
            continue
        fields = {}
        for part in variants:
            for name, rule in part.get('properties', {}).items():
                if rule not in fields.setdefault(name, []): fields[name].append(rule)
        properties = {}
        for name, rules in fields.items():
            if len(rules) == 1:
                properties[name] = rules[0]
            elif all('enum' in rule and set(rule) <= {'type', 'enum', 'description'}
                     and rule.get('type') == rules[0].get('type') for rule in rules):
                values = []
                for rule in rules:
                    for value in rule['enum']:
                        if value not in values: values.append(value)
                properties[name] = {'type': rules[0]['type'], 'enum': values}
            else:
                properties[name] = {'anyOf': rules}
        schema['properties'] = properties
        schema['required'] = [name for name in variants[0].get('required', [])
                              if all(name in part.get('required', []) for part in variants)]
    return tools


def native_specifications(scope='project'):
    return [t for t in specifications(scope) if t['name'][7:] not in (*GOAL_TOOLS,*WEB_TOOLS)]


def tools_for(scope='project'):
    return tuple(item['name'][7:] for item in catalog()[tool_scope(scope)])


def permission_tools(scope='project'):
    grouped={'read_roadmap','update_roadmap','cleanup_roadmap','read_environment_notes','record_environment_note',*GOAL_TOOLS,*WEB_TOOLS}
    return tuple(name for name in tools_for(scope) if name not in grouped)+('skill_network',)


def validate_arguments(name,value,scope='project'):
    if name in ('deploy_project','run_project') and isinstance(value,dict) and any(key in value for key in ('desktopShortcut','desktopLink')):
        raise ValueError('Studio desktop automation was removed. Use normal deploy/run or the project VM SSH tool for a requested guest shortcut.')
    definition=next((item for item in catalog()[tool_scope(scope)] if item['name']=='studio_'+name),None)
    if definition is None:raise ValueError('This tool is unavailable for this workspace kind.')
    root=definition['inputSchema']

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
            matched = 0
            for candidate in rule['oneOf']:
                try: validate(candidate, v, path); matched += 1
                except ValueError: pass
            if matched != 1:
                selected = [candidate for candidate in rule['oneOf'] if selects(candidate, v)]
                if matched == 0 and len(selected) == 1:
                    validate(selected[0], v, path)
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
    if (name == 'update_roadmap'
            and value.get('operation') == 'mutate' and value.get('action') == 'create'):
        kind = value['target']['kind']
        required = 'title' if kind in ('version', 'subversion') else 'description'
        if required not in value['input']:
            raise ValueError('arguments.input: ' + kind + ' create requires ' + required + '.')
