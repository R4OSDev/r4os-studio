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


def profile(root, projects, pinned=None, resolve_rust=True):
    defaults = pinned or json.loads((root / 'Profiles/versions.json').read_text())['defaults']
    sdk_id = defaults['sdk'].get('revision')
    contract_id = defaults['contract'].get('revision')
    zig_id = defaults['zig'].get('version')
    if not all(isinstance(v, str) and re.fullmatch('[a-f0-9]{40}', v) for v in (sdk_id, contract_id)) or not re.fullmatch(r'\d+\.\d+\.\d+', zig_id or ''):
        raise ValueError('Select installed SDK, Contract and Zig components.')
    paths = {'sdk': root / 'SDK' / sdk_id, 'contract': root / 'Contract' / contract_id,
             'zig': root / 'Toolchains/Zig' / zig_id}
    pins = {}; records = {}
    for kind, path in paths.items():
        if path.resolve(strict=True) != path.absolute():
            raise ValueError('Invalid component path.')
        marker = path / '.studio-component.json'
        record = json.loads(marker.read_text()); records[kind] = record
        if not re.fullmatch('[a-f0-9]{64}', record.get('sha256', '')):
            raise ValueError('Missing component checksum.')
        pins[kind] = {key: record[key] for key in ('version', 'revision', 'sha256', 'url') if key in record}
        pins[kind]['url'] = record.get('url') or record['archiveUrl']
        if kind != 'zig':
            pins[kind]['zigPackageHash'] = record.get('zigPackageHash') or record.get('packageHash')
    pins['zig']['binarySha256'] = digest(paths['zig'] / 'zig')
    if records['zig'].get('binarySha256', pins['zig']['binarySha256']) != pins['zig']['binarySha256']:
        raise ValueError('Compiler checksum does not match its installed metadata.')
    if pinned and pins != {key: value for key, value in pinned.items() if key not in ('rust', 'sdkTools')}:
        raise ValueError('Pinned project components changed.')
    from service import parse_package_info
    dependency = parse_package_info((paths['sdk'] / 'build.zig.zon').read_text())['dependencies']['contract']
    if not (pinned or {}).get('rust') and (dependency['revision'] != contract_id or dependency['packageHash'] != pins['contract']['zigPackageHash']):
        raise ValueError('The selected Contract differs from the selected SDK dependency. Select its matching Contract in Updates.')
    key = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()
    cache = projects / '.studio/tools' / key
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(cache),
           'ZIG_LOCAL_CACHE_DIR': str(cache / 'local'), 'ZIG_GLOBAL_CACHE_DIR': str(cache / 'global')}
    (cache / 'build.zig').write_text('pub fn build(b: *@import("std").Build) void { _ = b; }\n')
    zig = paths['zig'] / 'zig'
    with (cache / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if run([zig, 'version'], env) != zig_id:
            raise ValueError('Compiler version does not match the selected profile.')
        for kind in ('sdk', 'contract'):
            if run([zig, 'fetch', paths[kind]], env) != pins[kind]['zigPackageHash']:
                raise ValueError('Component package checksum changed.')
    revision = template_revision(pins)
    context = {'pins': pins, 'revision': revision, 'templateRevision': revision,
               'paths': paths, 'cache': cache, 'env': env}
    from rust_projects import local, runner
    from toolset import prepare as prepare_tools
    with (cache / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Older project records retain their original source/pin format. New
        # records bind the SDK's published toolset without a revision registry.
        if not pinned or pinned.get('sdkTools'):
            tools = prepare_tools(context, (pinned or {}).get('sdkTools'))
            context.update(sdkTools=tools, capabilities=tools['capabilities'], tool=tools['catalog'])
            context['pins']['sdkTools'] = tools['pin']
        else:
            tool = cache / 'module-catalog'; marker = cache / 'tool.json'
            if not tool.is_file() or not marker.is_file() or digest(tool) != json.loads(marker.read_text()).get('sha256'):
                run([zig, 'build-exe', '-OReleaseSafe', '--dep', 'contract_bundle',
                     '-Mroot=' + str(paths['sdk'] / 'Tools/ModuleCatalog/src/main.zig'), '--dep', 'r4os_contract',
                     '-Mcontract_bundle=' + str(paths['sdk'] / 'r4os/r4cp_convert.zig'),
                     '-Mr4os_contract=' + str(paths['contract'] / 'Generated/SDK/Zig/package.zig'), '-femit-bin=' + str(tool)], env)
                marker.write_text(json.dumps({'sha256': digest(tool)}))
            context['tool'] = tool
        context['runner'] = runner(root, defaults)
        if resolve_rust:
            try: context['rust'] = local(root, defaults, context, (pinned or {}).get('rust'))
            except (OSError, ValueError, KeyError) as error:
                if (pinned or {}).get('rust'): raise ValueError('Pinned project Rust tools changed: ' + str(error)) from error
                context['rustError'] = str(error)
        if (pinned or {}).get('rust'): context['pins']['rust'] = context['rust']['pin']
    context['templateRevision'] = template_revision(context['pins'])
    context['revision'] = hashlib.sha256((context['templateRevision'] + json.dumps(context['rust']['pin'] if context.get('rust') else context.get('rustError'), sort_keys=True)).encode()).hexdigest()
    return context


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
    plan = json.loads(run([tool, 'plan', '--manifest', directory / 'module.R4MF'], context['env'])) if catalog['entries'][0]['kind'] == 'R4X' else None
    contract_plan = run([tool, 'contract-plan', '--manifest', directory / 'module.R4MF'], context['env']) if plan else None
    return {'catalog': catalog, 'plan': plan, 'contractPlan': contract_plan}


def main():
    os.umask(0o077)
    request = json.loads(sys.stdin.buffer.read(131073))
    projects, root = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    context = profile(root, projects, request.get('pins'))
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
