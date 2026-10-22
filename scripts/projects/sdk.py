"""Pinned SDK adapter; Studio never reimplements the R4MF grammar."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

SUPPORTED = {
    '2fdc71e11d6a26fd1998dfddb43923f9d707abda': '03195b2a2e7461c72a4d0d6b645ae24319ba6315',
    '0508853ba75f4d6e8b7bbe8515fa63ed0d314da1': '95f762623e6ac2025e9a8aa781713c7c957629a8',
    '41770f2c354e461a5663ad805b7b2955dab1d5a9': '95f762623e6ac2025e9a8aa781713c7c957629a8',
}
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
    rust_pair = (pinned or {}).get('rust') and sdk_id == '41770f2c354e461a5663ad805b7b2955dab1d5a9' and contract_id == '50a38becae5765e0f85f6af6713fc72e00583952'
    if (SUPPORTED.get(sdk_id) != contract_id and not rust_pair) or zig_id != '0.16.0':
        raise ValueError('Select a verified SDK/Contract profile with Zig 0.16.0.')
    paths = {'sdk': root / 'SDK' / sdk_id, 'contract': root / 'Contract' / contract_id,
             'zig': root / 'Toolchains/Zig' / zig_id}
    pins = {}
    for kind, path in paths.items():
        if path.resolve(strict=True) != path.absolute():
            raise ValueError('Invalid component path.')
        marker = path / '.studio-component.json'
        record = json.loads(marker.read_text())
        if not re.fullmatch('[a-f0-9]{64}', record.get('sha256', '')):
            raise ValueError('Missing component checksum.')
        pins[kind] = {key: record[key] for key in ('version', 'revision', 'sha256', 'url') if key in record}
        pins[kind]['url'] = record.get('url') or record['archiveUrl']
        if kind != 'zig':
            pins[kind]['zigPackageHash'] = record.get('zigPackageHash') or record.get('packageHash')
    pins['zig']['binarySha256'] = digest(paths['zig'] / 'zig')
    if pins['zig']['binarySha256'] != '2317bbb91798556d9d0f38aabdac23db83f0979b25f767259ae474546724087c':
        raise ValueError('Compiler version or checksum does not match the verified Linux x86_64 profile.')
    if pinned and pins != {key: value for key, value in pinned.items() if key != 'rust'}:
        raise ValueError('Pinned project components changed.')
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
        tool = cache / 'module-catalog'
        marker = cache / 'tool.json'
        if not tool.is_file() or not marker.is_file() or digest(tool) != json.loads(marker.read_text()).get('sha256'):
            temp = cache / 'module-catalog.new'
            run([zig, 'build-exe', '-OReleaseSafe', '--dep', 'contract_bundle',
                 '-Mroot=' + str(paths['sdk'] / 'Tools/ModuleCatalog/src/main.zig'), '--dep', 'r4os_contract',
                 '-Mcontract_bundle=' + str(paths['sdk'] / 'r4os/r4cp_convert.zig'),
                 '-Mr4os_contract=' + str(paths['contract'] / 'Generated/SDK/Zig/package.zig'),
                 '-femit-bin=' + str(temp)], env)
            os.replace(temp, tool)
            marker.write_text(json.dumps({'sha256': digest(tool)}))
    revision = hashlib.sha256((key + ':templates-v1').encode()).hexdigest()
    context = {'pins': pins, 'revision': revision, 'templateRevision': revision,
               'paths': paths, 'cache': cache, 'env': env, 'tool': tool}
    if resolve_rust and sdk_id == '41770f2c354e461a5663ad805b7b2955dab1d5a9':
        from rust_projects import local, prepare
        from rust_sdk import SPEC
        context['templateRevision'] = hashlib.sha256((key + ':templates-v2').encode()).hexdigest()
        # Capabilities describe SDK support independently of the selected compiler.
        prefix = root / 'Toolchains/Rust' / SPEC['id']
        if (prefix / 'Tools/RustToolsProfile.json').is_file():
            try:
                exported = json.loads((prefix / 'Tools/RustToolsProfile.json').read_text())
                if digest(prefix / 'Tools/RustToolsProfile.json') != SPEC['release']['devkit']['profile_sha256']:
                    raise ValueError('The SDK Rust capability profile checksum changed.')
                with (cache / 'lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    declared = prepare(context, {'prefix': prefix, 'profile': exported,
                                                 'pin': {'toolProfileSha256': SPEC['release']['devkit']['profile_sha256']}})
                    context['capabilities'] = declared['capabilities']
            except (OSError, ValueError, KeyError):
                context['rustError'] = 'The SDK Rust capability files could not be verified.'
        try:
            with (cache / 'lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                context['rust'] = prepare(context, local(root, defaults, sdk_id, (pinned or {}).get('rust')))
        except (OSError, ValueError, KeyError) as error:
            if (pinned or {}).get('rust'):
                raise ValueError('Pinned project Rust tools changed.') from error
            context.setdefault('rustError', str(error) if str(error).startswith(('Select the SDK', 'The SDK Rust', 'An SDK Rust', 'The selected')) else 'The SDK Rust toolchain is unavailable. Download it in Updates → Tools → Rust.')
        if (pinned or {}).get('rust'):
            context['pins']['rust'] = context['rust']['pin']
            context['templateRevision'] = hashlib.sha256((json.dumps(context['pins'], sort_keys=True) + ':rust-templates-v2').encode()).hexdigest()
        selection = context['rust']['pin'] if context.get('rust') else context.get('rustError')
        context['revision'] = hashlib.sha256((context['templateRevision'] + json.dumps(selection, sort_keys=True)).encode()).hexdigest()
    return context


def options(context):
    from rust_projects import combination
    modules = []
    for template in TYPES:
        ident, label, kind, app_class, languages = template
        match = combination(context, template)
        modules.append({'id': ident, 'label': label, 'kind': kind, 'appClass': app_class,
                        'languages': [*languages, *(['Rust'] if match and match['supported'] and match['qualified'] else [])],
                        'available': True, 'reasons': {'Rust': match['reason'] if match else context.get('rustError', 'Rust projects require a compatible SDK.')}})
    matches = [combination(context, value) for value in TYPES]
    supported = any(v and v['supported'] for v in matches)
    qualified = any(v and v['supported'] and v['qualified'] for v in matches)
    ready = qualified and bool(context.get('rust'))
    return {'revision': context['revision'], 'profile': context['pins'],
            'languages': [{'id': language, 'available': language != 'Rust' or ready,
                           **({'supported': supported, 'toolsAvailable': bool(context.get('rust')),
                               'executionQualified': qualified,
                               **({'reason': context.get('rustError', 'Rust projects require a compatible SDK.')} if not ready else {})} if language == 'Rust' else {})}
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
        message = str(error) if str(error).startswith(('Select a verified', 'Pinned project', 'Component package', 'Compiler version')) else 'The SDK profile could not be validated. Check the installed SDK, Contract and Zig versions.'
        print(json.dumps({'error': message, 'code': 503}))
        sys.exit(1)
