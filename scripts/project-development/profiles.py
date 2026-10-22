"""Fail-closed execution eligibility; build availability is resolved by the SDK."""
import json
from contracts import APP, DevelopmentFault, hash_value


def catalog():
    path = APP / 'shared/r4os/development-profiles.json'
    try: value = json.loads(path.read_text())
    except (OSError, ValueError): raise DevelopmentFault('Development qualification profiles are unavailable.', 503)
    if value.get('schema') != 1 or value.get('interface') != 'r4os-studio-execution-profiles' or not isinstance(value.get('profiles'), list):
        raise DevelopmentFault('The development qualification schema is not supported.', 503)
    return value


def eligible(project, image):
    """Never interpret matching version labels as matching component identities."""
    if not image:
        return {'available': False, 'profileId': None, 'reason': 'Assign an available virtual machine in Project settings.'}
    for profile in catalog()['profiles']:
        target = profile['image']
        if image.get('id') != target['id'] or image.get('sha256') != target['sha256']:
            continue
        language = project['language']
        # SDK/compiler identities are project pins checked by preparation and
        # build receipts. The runner qualifies the image and role adapter only.
        roles = profile.get('qualifiedRoles', {})
        if language not in roles.get(project['template'], []):
            return {'available': False, 'profileId': profile['id'],
                    'reason': profile.get('roleReasons', {}).get(project['template'], 'This module role needs a qualified guest execution or test-host adapter.')}
        return {'available': True, 'profileId': profile['id'], 'qualificationSha256': hash_value(profile)}
    return {'available': False, 'profileId': None,
            'reason': 'This VM image has not been qualified for Studio development. Its existing image binding is preserved.'}


def require_profile(project, image):
    result = eligible(project, image)
    if not result['available']: raise DevelopmentFault(result['reason'])
    return next(p for p in catalog()['profiles'] if p['id'] == result['profileId'])
