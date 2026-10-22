"""Consume the published capability interface and official Rust creator/build driver."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))
from rust_sdk import verify, verify_files, environment, command, digest


def runner(root, defaults):
    selected = defaults.get('rust', {}).get('id', '')
    prefixes = [root / 'Toolchains/Rust' / selected] if selected and '/' not in selected else []
    prefixes += sorted((root / 'Toolchains/Rust').glob('*'))
    for prefix in prefixes:
        if prefix.resolve() != prefix.absolute() or not (prefix / 'PowerShell/pwsh').is_file(): continue
        value = json.loads((prefix / '.studio-component.json').read_text())
        path = prefix / 'PowerShell/pwsh'
        if value.get('fileHashes', {}).get('PowerShell/pwsh') == digest(path):
            verify_files(prefix, {key: checksum for key, checksum in value['fileHashes'].items() if key.startswith('PowerShell/')})
            return path
    return None


def local(root, defaults, context, pinned=None):
    from rust_sdk import compiler_path
    selected = pinned or defaults.get('rust')
    if not selected or not isinstance(selected.get('id'), str) or '/' in selected['id'] or selected['id'] in ('.', '..'):
        raise ValueError('Select an installed SDK Rust toolchain in Updates.')
    prefix = root / 'Toolchains/Rust' / selected['id']
    if prefix.resolve(strict=True) != prefix.absolute(): raise ValueError('Invalid SDK Rust installation path.')
    record = json.loads((prefix / '.studio-component.json').read_text()); verify(prefix, record)
    compiler = compiler_path(prefix); toolchain = prefix / compiler.parent.parent
    if context.get('sdkTools'):
        tools = context['sdkTools']
    else:
        exported = json.loads((prefix / 'Tools/RustToolsProfile.json').read_text())
        release_raw = (prefix / 'SDK-Release.json').read_bytes()
        tools = {'tools': prefix / 'Tools', 'profile': exported,
                 'capabilities': json.loads((prefix / 'capabilities.json').read_text()),
                 'release': json.loads(release_raw), 'pin': {'releaseSha256': hashlib.sha256(release_raw).hexdigest(),
                 'profileSha256': digest(prefix / 'Tools/RustToolsProfile.json')}}
    profile = tools['profile']; release = tools['release']
    if record['version'] != profile['rust_version'] or record['cargoVersion'] != profile['cargo_version']:
        raise ValueError('The selected Rust compiler differs from the SDK requirement: Rust ' + profile['rust_version'] + '.')
    for kind in ('sdk', 'contract'):
        verify_files(context['paths'][kind], {v['path']: v['sha256'] for v in profile[kind]['inputs']})
    contract = context['paths']['contract']; linker = toolchain / 'lib/rustlib/x86_64-unknown-linux-gnu/bin/rust-lld'
    target_prefix = str(compiler.parent.parent / 'lib/rustlib' / profile['bare_target']) + '/'
    sysroot = {key: value for key, value in record['fileHashes'].items() if key.startswith(target_prefix)}
    pin = {'id': selected['id'], 'version': record['version'], 'cargoVersion': record['cargoVersion'],
           'sha256': record['sha256'], 'toolProfileSha256': tools['pin']['profileSha256'],
           'binarySha256': digest(prefix / compiler), 'cargoSha256': digest(toolchain / 'bin/cargo'),
           'linkerSha256': digest(linker), 'powershellSha256': digest(prefix / 'PowerShell/pwsh'),
           'installationSha256': hashlib.sha256(json.dumps({'files': record['fileHashes'], 'symlinks': record['symlinks']}, sort_keys=True).encode()).hexdigest(),
           'sysrootSha256': hashlib.sha256(json.dumps(sysroot, sort_keys=True).encode()).hexdigest(),
           'rustupVersion': profile['rustup_version'], 'powershellVersion': record['powershellVersion'], 'target': profile['bare_target'],
           'codegenProfile': json.loads((context['paths']['sdk'] / 'r4os/rust_module_profile.json').read_text())['id'],
           'codegenSha256': digest(context['paths']['sdk'] / 'r4os/rust_module_profile.json'), 'cpuBaselineSha256': digest(contract / 'Module/CpuBaseline.json'),
           'release': {'url': 'https://github.com/R4OSDev/r4os-sdk/releases/download/v' + release['sdk']['package_version'] + '/SDK-Release.json',
                       'sha256': tools['pin']['releaseSha256'], 'sdkRevision': release['sdk']['source_commit'],
                       'contractRevision': release['contract']['source_commit'], 'devkitRevision': release['devkit']['source_commit'],
                       'capabilitiesSha256': release['capabilities']['package']['sha256']}}
    if pinned and pin != pinned: raise ValueError('Pinned project Rust tools changed.')
    result = {'prefix': prefix, 'profile': profile, 'pin': pin, 'compiler': compiler, 'contractPath': contract,
              'contractPin': context['pins']['contract'], 'tools': tools['tools'],
              'catalog': tools['tools'] / profile['hosts']['Linux']['catalog'], 'capabilities': tools['capabilities'],
              'env': environment(prefix, context['cache'])}
    context['capabilities'] = tools['capabilities']
    return result


def build(context, directory, output=None):
    rust = context['rust']
    output = output or directory / 'build'
    args = [rust['prefix'] / 'PowerShell/pwsh', '-NoLogo', '-NoProfile', '-File',
                    context['paths']['sdk'] / 'Tools/Build-RustModule.ps1', '-ProjectRoot', directory,
                    '-SdkRoot', context['paths']['sdk'], '-ContractRoot', context['paths']['contract'],
                    '-ToolsRoot', rust['tools'], '-InstallRoot', rust['prefix'] / 'Install',
                    '-CacheRoot', context['cache'] / 'rust-build-cache', '-OutputRoot', output]
    if context.get('sdkTools'): args += ['-ZigRoot', context['paths']['zig']]
    return command(args, rust['env'], context['cache'], timeout=180)
