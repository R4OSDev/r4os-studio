"""Consume the published capability interface and official Rust creator/build driver."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))
from rust_sdk import SPEC, COMPILER, verify, verify_files, environment, command, digest


def local(root, defaults, sdk_id, pinned=None):
    selected = pinned or defaults.get('rust')
    if sdk_id != SPEC['release']['sdk']['source_commit']:
        raise ValueError('Rust projects require a compatible SDK.')
    if not selected or selected.get('id') != SPEC['id']:
        raise ValueError('Select the SDK 0.64.66 Rust toolchain in Updates → Tools → Rust.')
    prefix = root / 'Toolchains/Rust' / selected['id']
    if prefix.resolve(strict=True) != prefix.absolute():
        raise ValueError('Invalid SDK Rust installation path.')
    record = json.loads((prefix / '.studio-component.json').read_text())
    verify(prefix, record)
    profile = json.loads((prefix / 'Tools/RustToolsProfile.json').read_text())
    contract = root / 'Contract' / SPEC['release']['contract']['source_commit']
    if not contract.is_dir():
        raise ValueError('The SDK Rust Contract is missing. Download the SDK Rust toolchain in Updates → Tools → Rust.')
    if contract.resolve(strict=True) != contract.absolute():
        raise ValueError('Invalid SDK Rust Contract path.')
    metadata = json.loads((contract / '.studio-component.json').read_text())
    if metadata.get('revision') != SPEC['release']['contract']['source_commit']:
        raise ValueError('The SDK Rust Contract revision is unavailable.')
    contract_pin = {key: metadata[key] for key in ('version', 'revision', 'sha256')}
    contract_pin.update(url=metadata.get('url') or metadata['archiveUrl'],
                        zigPackageHash=metadata.get('zigPackageHash') or metadata['packageHash'])
    toolchain = prefix / Path(COMPILER).parent.parent
    linker = toolchain / 'lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-lld'
    target_prefix = str(Path(COMPILER).parent.parent / 'lib/rustlib' / profile['bare_target']) + '/'
    sysroot = {key: value for key, value in record['fileHashes'].items() if key.startswith(target_prefix)}
    pin = {'id': SPEC['id'], 'version': record['version'], 'cargoVersion': record['cargoVersion'],
           'sha256': record['sha256'], 'toolProfileSha256': record['manifestSha256'],
           'binarySha256': digest(prefix / COMPILER), 'cargoSha256': digest(toolchain / 'bin/cargo'),
           'linkerSha256': digest(linker), 'powershellSha256': digest(prefix / 'PowerShell/pwsh'),
           'installationSha256': hashlib.sha256(json.dumps({'files': record['fileHashes'], 'symlinks': record['symlinks']}, sort_keys=True).encode()).hexdigest(),
           'sysrootSha256': hashlib.sha256(json.dumps(sysroot, sort_keys=True).encode()).hexdigest(),
           'rustupVersion': profile['rustup_version'], 'powershellVersion': record['powershellVersion'],
           'target': profile['bare_target'],
           'codegenProfile': json.loads((root / 'SDK' / sdk_id / 'r4os/rust_module_profile.json').read_text())['id'],
           'codegenSha256': digest(root / 'SDK' / sdk_id / 'r4os/rust_module_profile.json'),
           'cpuBaselineSha256': digest(contract / 'Module/CpuBaseline.json'),
           'release': {'url': SPEC['releaseUrl'], 'sha256': SPEC['releaseSha256'],
                       'sdkRevision': SPEC['release']['sdk']['source_commit'],
                       'contractRevision': SPEC['release']['contract']['source_commit'],
                       'devkitRevision': SPEC['release']['devkit']['source_commit'],
                       'capabilitiesSha256': SPEC['release']['capabilities']['package']['sha256']}}
    if pinned and pin != pinned:
        raise ValueError('Pinned project Rust tools changed.')
    return {'prefix': prefix, 'profile': profile, 'pin': pin, 'contractPath': contract, 'contractPin': contract_pin}


def prepare(context, rust):
    for kind in ('sdk', 'contract'):
        path = rust.get('contractPath', context['paths']['contract']) if kind == 'contract' else context['paths'][kind]
        try:
            verify_files(path, {v['path']: v['sha256'] for v in rust['profile'][kind]['inputs']})
        except ValueError as error:
            raise ValueError('The selected ' + kind.upper() + ' files do not match the SDK Rust profile.') from error
    # Official scripts chmod the catalog. Give them a checked private copy, not
    # write access to the shared component tree or hardlinks into that tree.
    target = context['cache'] / 'rust-tools'
    source = rust['prefix'] / 'Tools'
    expected = {v['path']: v['sha256'] for v in rust['profile']['files']}
    expected['RustToolsProfile.json'] = rust['pin']['toolProfileSha256']
    if target.exists():
        verify_files(target, expected)
    else:
        temporary = target.with_name('rust-tools.new')
        if temporary.exists():
            shutil.rmtree(temporary)
        shutil.copytree(source, temporary)
        verify_files(temporary, expected)
        temporary.rename(target)
    catalog = target / rust['profile']['hosts']['Linux']['catalog']
    catalog.chmod(0o755)
    env = environment(rust['prefix'], context['cache'])
    raw = command([catalog, 'capabilities', '--json', '--profile', target / 'RustToolsProfile.json'],
                  {'PATH': '', 'HOME': str(context['cache'])}, context['cache'])
    capabilities = json.loads(raw)
    if capabilities.get('schema') != 2 or capabilities.get('interface') != 'r4os-sdk-capabilities' or capabilities.get('technical'):
        raise ValueError('Unsupported or technical SDK capability catalog.')
    if capabilities != json.loads((rust['prefix'] / 'capabilities.json').read_text()):
        raise ValueError('The SDK capability catalog changed.')
    rust.update(tools=target, catalog=catalog, env=env, capabilities=capabilities)
    return rust


def combination(context, template):
    cap = context.get('capabilities') or context.get('rust', {}).get('capabilities')
    if not cap:
        return None
    _, _, kind, app_class, _ = template
    role = 'subsystem' if template[0] == 'subsystem' else None
    support = next((v for v in cap['support'] if v['language'] == 'Rust' and v['kind'] == kind
                    and v['app_class'] == app_class and v['role'] == role
                    and v['entry_mode'] == ('app' if kind == 'R4X' else None) and v['execution'] == 'host'
                    and 'Linux' in v['hosts']), None)
    candidate = next((v for v in cap['templates'] if v['language'] == 'Rust' and v['kind'] == kind
                      and v['app_class'] == app_class and v['role'] == role and v['entry_mode'] == 'app'
                      and v['execution'] == 'host' and v['supported']), None)
    qualified = app_class in cap['qualification']['linux_host_build']
    return {'supported': bool(support and support['supported'] and candidate),
            'qualified': qualified,
            'reason': support['reason'] if support else 'This SDK does not declare this Rust combination.',
            'template': candidate}


def render(context, directory, project, template):
    from sdk import validate
    match = combination(context, template)
    if not match or not match['supported'] or not match['qualified']:
        raise ValueError(match['reason'] if match else context.get('rustError', 'Rust tools are unavailable.'))
    rust = context['rust']
    command([rust['prefix'] / 'PowerShell/pwsh', '-NoLogo', '-NoProfile', '-File',
             context['paths']['sdk'] / rust['capabilities']['project_creation']['rust_driver'],
             '-TemplateId', match['template']['id'], '-Directory', directory,
             '-ProjectName', project['moduleName'], '-SdkRoot', context['paths']['sdk'],
             '-ContractRoot', context['paths']['contract'], '-ToolsRoot', rust['tools']],
            rust['env'], context['cache'])
    for name in ('LICENSE', 'NOTICE'):
        if (context['paths']['sdk'] / name).is_file():
            shutil.copyfile(context['paths']['sdk'] / name, directory / (name + '.R4OS-SDK'))
    (directory / 'THIRD_PARTY_NOTICES.md').write_text('Generated by the official R4OS SDK Rust project creator at '
        + context['pins']['sdk']['revision'] + '.\nSee LICENSE.R4OS-SDK and NOTICE.R4OS-SDK.\n')
    if (directory / 'r4os-project.json').exists() or '-ProjectPin' in (directory / 'Build.ps1').read_text():
        raise ValueError('The SDK emitted obsolete project pin metadata.')
    return validate(context, directory)


def build(context, directory, output=None):
    rust = context['rust']
    output = output or directory / 'build'
    return command([rust['prefix'] / 'PowerShell/pwsh', '-NoLogo', '-NoProfile', '-File',
                    context['paths']['sdk'] / 'Tools/Build-RustModule.ps1', '-ProjectRoot', directory,
                    '-SdkRoot', context['paths']['sdk'], '-ContractRoot', context['paths']['contract'],
                    '-ToolsRoot', rust['tools'], '-InstallRoot', rust['prefix'] / 'Install',
                    '-CacheRoot', context['cache'] / 'rust-build-cache', '-OutputRoot', output],
                   rust['env'], context['cache'], timeout=180)
