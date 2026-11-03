"""Pinned SDK adapter; Studio never reimplements the R4MF grammar."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from templates import revision as template_revision

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))

TYPES = [
    ('terminal', 'Terminal application', 'R4X', 'console', ['Zig', 'C']),
    ('desktop', 'Desktop application', 'R4X', 'gui', ['Zig', 'C']),
    ('service', 'Service', 'R4X', 'service', ['Zig', 'C']),
    ('driver', 'Driver', 'R4D', None, ['Zig']),
    ('protocol', 'Protocol module', 'R4P', None, ['Zig']),
    ('library', 'Runtime library', 'R4L', None, ['Zig', 'C']),
    ('subsystem', 'Subsystem host', 'R4X', 'gui', ['Zig', 'C']),
]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(args, env, timeout=120):
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True, env=env, timeout=timeout, cwd=env['HOME'])
    if result.returncode:
        raise ValueError((result.stderr or result.stdout)[-1600:])
    return result.stdout.strip()


def selection_revision(root, defaults, template):
    # Availability does not require reading compiler/sysroot bytes. Bind the
    # selection token to installed metadata so the dialog and submit agree.
    selected = defaults.get('rust', {}).get('id')
    rust = {'id': selected}
    if isinstance(selected, str) and selected not in ('', '.', '..') and '/' not in selected:
        try: rust['metadataSha256'] = digest(root / 'Toolchains/Rust' / selected / '.studio-component.json')
        except OSError: pass
    return hashlib.sha256((template + json.dumps(rust, sort_keys=True)).encode()).hexdigest()


def profile(root, projects, pinned=None, resolve_rust=True, verify_components=True, selected=None):
    from sdk_profiles import profile as sdk_owned_profile
    return sdk_owned_profile(root, projects, pinned, resolve_rust, verify_components, selected)


def options(context):
    from toolset import combination
    modules = []
    for template in TYPES:
        ident, label, kind, app_class, _ = template
        matches = {language: combination(context, template, language) for language in ('Rust', 'Zig', 'C')}
        modules.append({'id': ident, 'label': label, 'kind': kind, 'appClass': app_class,
                        'languages': [language for language, match in matches.items() if match and match['supported']],
                        'available': True, 'reasons': {language: match['reason'] if match else 'The SDK template is unavailable.' for language, match in matches.items()}})
    return {'revision': context['revision'], 'profile': context['pins'],
            'languages': [{'id': language, 'available': bool(context.get('rust')) if language == 'Rust' else bool(context.get('runner')),
                          **({'supported': True, 'toolsAvailable': bool(context.get('rust')), 'executionQualified': True,
                              **({'reason': context.get('rustError', 'Install the SDK Rust tools in Updates.')} if not context.get('rust') else {})} if language == 'Rust' else {})}
                          for language in ('Rust', 'Zig', 'C')],
            'moduleTypes': modules, 'vms': [], 'vmsAvailable': True}


def validate(context, directory):
    if context.get('rust') and 'LANGUAGE=Rust' in (directory / 'module.R4MF').read_text():
        tool = context['rust']['catalog']
    else:
        tool = context['tool']
    run([tool, 'validate', '--manifest', directory / 'module.R4MF'], context['env'])
    catalog = json.loads(run([tool, 'catalog', '--root', directory], context['env']))
    if len(catalog['entries']) != 1:
        raise ValueError('Expected one project manifest.')
    plan = json.loads(run([tool, 'plan', '--manifest', directory / 'module.R4MF'], context['env']))
    from sdk_profiles import bind_manifest
    resolved = bind_manifest(context, directory, plan['plan'])
    contract_plan = run([tool, 'contract-plan', '--manifest', directory / 'module.R4MF'], context['env']) if catalog['entries'][0]['kind'] == 'R4X' else None
    return {'catalog': catalog, 'plan': plan, 'contractPlan': contract_plan, 'sdkProfile': resolved}


def main():
    os.umask(0o077)
    request = json.loads(sys.stdin.buffer.read(131073))
    projects, root = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    is_options = request['operation'] == 'options'
    needs_rust = is_options or request.get('project', {}).get('language') == 'Rust' or bool((request.get('pins') or {}).get('rust'))
    context = profile(root, projects, request.get('pins'), resolve_rust=needs_rust, verify_components=not is_options)
    if request['operation'] == 'options':
        result = options(context)
    elif request['operation'] == 'render':
        from templates import render
        directory = Path(request['directory'])
        if not directory.is_relative_to(projects / '.studio/staging'):
            raise ValueError('Invalid project staging path.')
        result = render(context, directory, request['project'])
    elif request['operation'] == 'validate':
        directory = Path(request['directory'])
        if directory.resolve(strict=True) != directory.absolute() or not directory.is_relative_to(projects):
            raise ValueError('Invalid project validation path.')
        result = validate(context, directory)
    else:
        raise ValueError('Unsupported SDK operation.')
    print(json.dumps({'result': result}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        message = str(error) if str(error).startswith(('Select installed', 'Pinned ', 'Component ', 'Compiler ', 'The selected ', 'The SDK ')) else 'The SDK profile could not be validated. Check the installed SDK, Contract and Zig versions.'
        print(json.dumps({'error': message, 'code': 503}))
        sys.exit(1)
