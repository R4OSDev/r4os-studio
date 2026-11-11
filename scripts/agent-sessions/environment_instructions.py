"""Show the project's selected development inputs."""
import json


def compose(project, config):
    pins = config.get('projectPins', project.get('pins', {}))
    context = {'language': project.get('language'), 'role': project.get('template')}
    for name in ('sdk', 'contract', 'zig', 'rust'):
        value = pins.get(name)
        if isinstance(value, dict):
            context[name] = {key: value[key] for key in ('version', 'revision') if key in value}
    return '\n\nSTUDIO PROJECT ENVIRONMENT: ' + json.dumps(context, ensure_ascii=True, separators=(',', ':'))
