"""Explicit workspace-local SDK inputs, frozen with the original build request.

The SDK resolves identities and source policy. This adapter only bounds paths,
freezes the selected inputs and translates them into the worker namespace.
"""
import hashlib
import json
from pathlib import Path
import re

from contracts import DevelopmentFault, relative

CONFIG = '.studio/sdk-inputs.json'


def object_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise DevelopmentFault('Duplicate SDK input field: ' + key, 400)
        value[key] = item
    return value


def local(root, name, directory=False):
    name = relative(name)
    if '.git' in name.split('/'):
        raise DevelopmentFault('Select a source directory, not Git internals.', 400)
    path = Path(root) / name
    try:
        canonical = path.resolve(strict=True)
    except OSError:
        raise DevelopmentFault('SDK input is missing from the workspace: ' + name, 400) from None
    if canonical != path.absolute() or (directory and not path.is_dir()):
        raise DevelopmentFault('SDK inputs must be existing unlinked workspace paths.', 400)
    return name


def read(root):
    root = Path(root)
    path = root / CONFIG
    if not path.exists() and not path.is_symlink():
        return {'schema': 1, 'additionalLibraries': [], 'development': None, 'configSha256': None, 'technical': False}
    if path.resolve(strict=True) != path.absolute() or not path.is_file() or path.stat().st_size > 65536:
        raise DevelopmentFault('SDK input selection must be an unlinked JSON file of at most 64 KiB.', 400)
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise DevelopmentFault('SDK input selection exceeds 64 KiB.', 400)
    try:
        value = json.loads(raw, object_pairs_hook=object_pairs)
    except (UnicodeError, ValueError):
        raise DevelopmentFault('Invalid .studio/sdk-inputs.json.', 400) from None
    if (not isinstance(value, dict) or set(value) - {'schema', 'additionalLibraries', 'development'}
            or type(value.get('schema')) is not int or value['schema'] != 1):
        raise DevelopmentFault('Unsupported SDK input selection schema.', 400)
    extras = value.get('additionalLibraries', [])
    if not isinstance(extras, list) or len(extras) > 32:
        raise DevelopmentFault('Select at most 32 additional library sources.', 400)
    names = set()
    for item in extras:
        if (not isinstance(item, dict) or set(item) - {'id', 'root', 'path', 'commit', 'tree'}
                or not {'id', 'root'}.issubset(item) or ('commit' in item) == ('tree' in item)):
            raise DevelopmentFault('Each additional library needs an id, root and one commit or vendored tree identity.', 400)
        if not isinstance(item['id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', item['id']):
            raise DevelopmentFault('Invalid additional library id.', 400)
        if item['id'].casefold() in names:
            raise DevelopmentFault('Additional library ids collide after case folding.', 400)
        names.add(item['id'].casefold())
        local(root, item['root'], True)
        if 'path' in item:
            local(root, item['root'] + '/' + relative(item['path']), True)
        if 'commit' in item:
            if not isinstance(item['commit'], str) or not re.fullmatch('[a-f0-9]{40}', item['commit']):
                raise DevelopmentFault('An additional library commit must be the full immutable Git identity.', 400)
        else:
            tree = item['tree']
            if (not isinstance(tree, dict) or set(tree) != {'algorithm', 'files', 'sha256'}
                    or tree['algorithm'] != 'r4os-files-sha256-lf-v1'
                    or not isinstance(tree['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', tree['sha256'])
                    or not isinstance(tree['files'], list) or not tree['files'] or len(tree['files']) > 4096):
                raise DevelopmentFault('Use a complete SDK vendored tree identity.', 400)
            paths = [relative(name) for name in tree['files']]
            if any('.git' in name.split('/') for name in paths) or len({name.casefold() for name in paths}) != len(paths):
                raise DevelopmentFault('Vendored source paths collide or contain Git internals.', 400)
    development = value.get('development')
    if development is not None:
        if (not isinstance(development, dict) or set(development) - {'sdkRoot', 'contractRoot', 'librariesRoot', 'profile'}
                or not {'sdkRoot', 'profile'}.issubset(development)):
            raise DevelopmentFault('Select an SDK Git source and an explicitly created Development receipt.', 400)
        for name, selected in development.items():
            local(root, selected, name != 'profile')
        receipt = root / development['profile']
        if not receipt.is_file() or receipt.stat().st_size > 2 * 1024 * 1024:
            raise DevelopmentFault('The Development receipt is missing or oversized.', 400)
    return {'schema': 1, 'additionalLibraries': extras, 'development': development,
            'configSha256': hashlib.sha256(raw).hexdigest(), 'technical': development is not None}


def git_roots(value):
    roots = {item['root'] for item in value['additionalLibraries'] if 'commit' in item}
    if value['development']:
        roots.update(path for key, path in value['development'].items() if key != 'profile')
    return roots


def git_metadata(path, roots):
    """Only selected standalone repositories; no credentials, hooks or host links."""
    parts = Path(path).parts
    if '.git' not in parts:
        return True
    index = parts.index('.git')
    if '/'.join(parts[:index]) not in roots:
        return False
    tail = parts[index + 1:]
    return (not tail or tail[0] in {'HEAD', 'index', 'objects', 'refs', 'packed-refs', 'shallow'}) and tail[:2] != ('objects', 'info')


def verify_inventory(value, files):
    paths = {item['path'] for item in files}
    for item in value['additionalLibraries']:
        if 'tree' in item:
            prefix = item['root'] + '/'
            actual = {name[len(prefix):] for name in paths if name.startswith(prefix) and '.git' not in name.split('/')}
            if actual != set(item['tree']['files']):
                raise DevelopmentFault('The vendored library file list does not cover its complete captured source tree.')
        elif item['root'] + '/.git/HEAD' not in paths:
            raise DevelopmentFault('A pinned library needs a standalone Git checkout. Git worktree links are unavailable in build inputs.')
    if value['development'] and value['development']['sdkRoot'] + '/.git/HEAD' not in paths:
        raise DevelopmentFault('Development SDK inputs need a standalone Git checkout.')


def virtual(name):
    return '/workspace/' + relative(name)


def arguments(value, root):
    """Write the SDK's own additional library format; do not resolve it here."""
    extras = [{**item, 'root': virtual(item['root'])} for item in value['additionalLibraries']]
    additional = Path(root) / 'additional-libraries.json'
    additional.write_text(json.dumps(extras) + '\n')
    development = value['development']
    paths = {name: virtual(development[key]) if development and key in development else '/' + name
             for name, key in (('sdk', 'sdkRoot'), ('contract', 'contractRoot'), ('libraries', 'librariesRoot'))}
    common = ['-ContractRoot', paths['contract'], '-LibrariesRoot', paths['libraries'],
              '-AdditionalLibrariesFile', '/cache/additional-libraries.json']
    if development:
        common += ['-DevelopmentProfile', virtual(development['profile'])]
    dependencies = [virtual(item['root']) + ('/' + item['path'] if item.get('path') else '') for item in value['additionalLibraries']]
    return paths, common, dependencies


def summary(root):
    try:
        value = read(root)
        return {'available': True, 'path': CONFIG, 'technical': value['technical'], 'configSha256': value['configSha256'],
                'additionalLibraries': [item['id'] for item in value['additionalLibraries']],
                'developmentProfile': (value['development'] or {}).get('profile')}
    except (DevelopmentFault, OSError, TypeError) as error:
        return {'available': False, 'path': CONFIG, 'reason': str(error)}
