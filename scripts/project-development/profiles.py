"""Runner capabilities, independent of project components and VM releases."""
import json
from contracts import APP, DevelopmentFault, hash_value


def runner():
    path = APP / 'shared/r4os/development-runner.json'
    try: value = json.loads(path.read_text())
    except (OSError, ValueError): raise DevelopmentFault('The development runner configuration is unavailable.', 503)
    if value.get('schema') != 1 or value.get('interface') != 'r4os-studio-development-runner' or not isinstance(value.get('roles'), list):
        raise DevelopmentFault('The development runner configuration is not supported.', 503)
    return value


def eligible(project, image):
    if not image:
        return {'available': False, 'profileId': None, 'reason': 'Assign an available virtual machine in Project settings.'}
    profile = runner()
    if project['template'] not in profile['roles']:
        return {'available': False, 'profileId': profile['id'],
                'reason': profile.get('roleReasons', {}).get(project['template'], 'This module role needs its own execution or test-host adapter.')}
    return {'available': True, 'profileId': profile['id'], 'adapterSha256': hash_value(profile)}


def require_profile(project, image):
    result = eligible(project, image)
    if not result['available']: raise DevelopmentFault(result['reason'])
    return runner()
