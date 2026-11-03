"""Project bindings to a complete SDK package, with no legacy runtime path."""
import hashlib
import fcntl
import json
from pathlib import Path
import shutil
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'components'))
import sdk_host
import sdk_package as package
import sdk_provision
from templates import revision as template_revision


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(record, kind):
    value = {key: record[key] for key in ('version', 'revision', 'sha256') if key in record}
    value['url'] = record.get('url') or record['archiveUrl']
    if kind != 'zig':
        value['zigPackageHash'] = record.get('zigPackageHash') or record['packageHash']
    return value


def profile(root, projects, pinned=None, resolve_rust=True, verify_components=True, selected=None):
    root, projects = Path(root), Path(projects)
    defaults = pinned or selected or package.decode(package.regular_bytes(root / 'Profiles/versions.json'))['defaults']
    revision = defaults.get('sdk', {}).get('revision')
    if pinned and not pinned.get('sdkProfile'):
        raise ValueError('The project requires explicit migration to SDK-owned profiles. No legacy SDK fallback is available.')
    if not isinstance(revision, str) or not package.COMMIT.fullmatch(revision):
        raise ValueError('Select a complete installed SDK package.')
    verification_work = projects / '.studio/sdk-verification' / revision
    verification_work.mkdir(parents=True, exist_ok=True, mode=0o700)
    if verification_work.resolve() != verification_work.absolute():
        raise ValueError('Invalid SDK verification workspace.')
    context = sdk_provision.verify(root, revision, sources=verify_components, work=verification_work)
    bundle, manifest, paths, base = context['record'], context['manifest'], context['paths'], context['base']
    pins = {kind: identity(bundle['components'][kind], kind) for kind in ('sdk', 'contract', 'libraries')}
    pins['zig'] = bundle['zig'].copy()
    for kind in ('contract', 'libraries', 'zig'):
        given = defaults.get(kind)
        if given and any(given.get(key, value) != value for key, value in pins[kind].items() if key in ('version', 'revision')):
            raise ValueError('The selected ' + kind + ' contradicts the SDK-owned component set.')
    projection_path = paths['tools'] / 'RustToolsProfile.json'
    projection = package.decode(package.regular_bytes(projection_path))
    if (projection.get('profile_sources') != bundle['profileSources']
            or projection.get('sdk', {}).get('source', {}).get('commit') != revision
            or projection.get('contract', {}).get('source', {}).get('commit') != pins['contract']['revision']):
        raise ValueError('The SDK matched-tool projection contradicts its original profile sources.')
    pins['sdkTools'] = {'url': package.release_url(manifest['sdk_version']),
                        'releaseSha256': bundle['manifestSha256'],
                        'archiveSha256': package.asset(manifest, 'tools')['sha256'],
                        'profileSha256': digest(projection_path),
                        'capabilitiesSha256': package.asset(manifest, 'capabilities')['sha256']}
    pins['sdkProfile'] = {'schema': 1, 'interface': package.INTERFACE, 'hashes': bundle['profileSources'],
                          'manifestSha256': bundle['manifestSha256'], 'technical': False}
    if pinned and pinned.get('sdkProfile', {}).get('id'):
        ident = pinned['sdkProfile']['id']
        item = manifest['profiles'].get(ident)
        if not item or item['role'] != 'module':
            raise ValueError('The pinned SDK module profile is missing.')
        pins['sdkProfile']['id'] = ident
    if pinned and pinned.get('sdkProfile', {}).get('templateId'):
        ident = pinned['sdkProfile']['templateId']
        if not any(value['id'] == ident and value['supported'] for value in context['capabilities']['templates']):
            raise ValueError('The pinned SDK template is unavailable.')
        pins['sdkProfile']['templateId'] = ident
    key = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()
    cache = projects / '.studio/tools' / key
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    if cache.resolve() != cache.absolute():
        raise ValueError('Invalid project SDK metadata cache.')
    runner = context['runner']
    # SDK helpers prepare executable permissions in ToolsRoot. They receive a
    # private exact copy, keeping shared packages read-only for project hosts.
    if verify_components:
        destination = cache / 'sdk-tools'
        with (cache / 'sdk-tools.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not destination.exists():
                staging = cache / 'sdk-tools.new'
                if staging.exists():
                    shutil.rmtree(staging)
                shutil.copytree(paths['tools'], staging)
                staging.rename(destination)
            if destination.resolve(strict=True) != destination.absolute():
                raise ValueError('Invalid project SDK tool cache.')
            for item in projection['files']:
                relative = package.relative(item['path'])
                target = destination / relative
                if target.resolve(strict=True) != target.absolute() or digest(target) != digest(paths['tools'] / relative):
                    raise ValueError('The private SDK tool cache differs from its verified original.')
        paths = {**paths, 'tools': destination}
        projection_path = destination / 'RustToolsProfile.json'
    native = projection['hosts']['Linux']
    catalog = paths['tools'] / package.relative(native['catalog'])
    if catalog.resolve(strict=True) != catalog.absolute():
        raise ValueError('The SDK catalog path changed.')
    env = sdk_host.environment(runner, cache)
    env.update(ZIG_GLOBAL_CACHE_DIR=str(cache / 'global'), ZIG_LOCAL_CACHE_DIR=str(cache / 'local'))
    result = {'pins': pins, 'paths': {key: paths[key] for key in ('sdk', 'contract', 'libraries', 'tools', 'install')},
              'cache': cache, 'env': env, 'runner': runner, 'tool': catalog,
              'capabilities': context['capabilities'], 'package': context,
              'sdkTools': {'tools': paths['tools'], 'profile': projection, 'pin': pins['sdkTools'],
                           'catalog': catalog, 'capabilities': context['capabilities'], 'release': manifest}}
    result['paths']['zig'] = paths['install'] / 'Toolchains/Zig'
    if verify_components:
        from sdk import run
        actual = package.decode(run([catalog, 'capabilities', '--json', '--profile', projection_path], env).encode())
        if actual != result['capabilities']:
            raise ValueError('The SDK native capability catalog differs from its published bytes.')
    if resolve_rust:
        rust = bundle['rust']
        compiler = Path(rust['toolchain']) / 'bin/rustc'
        cargo = compiler.with_name('cargo')
        linker = Path(rust['llvm_bin']) / 'rust-lld'
        for path in (compiler, cargo, linker):
            if not path.is_relative_to(base / 'Install'):
                raise ValueError('The SDK Rust installation is outside its verified package.')
        def file_hash(path):
            return bundle['hostFiles'][str(path.relative_to(base))]
        tool_files_hash = package.sha256(json.dumps({'files': bundle['hostFiles'], 'links': bundle['hostLinks']}, sort_keys=True).encode())
        rust_pin = {'id': 'sdk-' + manifest['sdk_version'], 'version': rust['rust_version'],
                    'cargoVersion': rust['cargo_version'], 'sha256': tool_files_hash,
                    'toolProfileSha256': pins['sdkTools']['profileSha256'], 'binarySha256': file_hash(compiler),
                    'cargoSha256': file_hash(cargo), 'linkerSha256': file_hash(linker),
                    'powershellSha256': digest(runner), 'installationSha256': tool_files_hash,
                    'sysrootSha256': tool_files_hash, 'rustupVersion': rust['rustup_version'],
                    'powershellVersion': package.decode(package.regular_bytes(root / 'Profiles/sdk-host.json'))['powershell']['version'],
                    'target': projection['bare_target'],
                    'codegenProfile': package.decode(package.regular_bytes(paths['sdk'] / 'r4os/rust_module_profile.json'))['id'],
                    'codegenSha256': digest(paths['sdk'] / 'r4os/rust_module_profile.json'),
                    'cpuBaselineSha256': digest(paths['contract'] / 'Module/CpuBaseline.json'),
                    'release': {'url': pins['sdkTools']['url'], 'sha256': bundle['manifestSha256'],
                                'sdkRevision': revision, 'contractRevision': pins['contract']['revision'],
                                'capabilitiesSha256': pins['sdkTools']['capabilitiesSha256']}}
        result['rust'] = {'prefix': base, 'compiler': compiler.relative_to(base), 'tools': paths['tools'],
                           'catalog': catalog, 'profile': projection, 'pin': rust_pin, 'contract': paths['contract'],
                           'linker': linker, 'install': paths['install']}
        if (pinned or {}).get('rust'):
            pins['rust'] = rust_pin
    if pinned and pins != pinned:
        raise ValueError('The pinned SDK package, profile or host tool identities changed.')
    result['templateRevision'] = template_revision(pins)
    result['revision'] = result['templateRevision']
    return result


def bind_manifest(context, directory, facts):
    """Record the profile selected by SDK facts, then ask the SDK to resolve it."""
    manifest = context['package']['manifest']
    if facts['language'] == 'Rust':
        ident = facts['rust_project']['profile']
    else:
        matches = [key for key, value in manifest['profiles'].items()
                   if value['language'] == facts['language'] and value['role'] == 'module']
        if len(matches) != 1:
            raise ValueError('The SDK does not identify one module profile for this language.')
        ident = matches[0]
    declared = manifest['profiles'].get(ident)
    if not declared or declared['language'] != facts['language'] or declared['role'] != 'module':
        raise ValueError('The SDK manifest plan selects an inconsistent module profile.')
    expected = context['pins']['sdkProfile'].get('id')
    if expected and expected != ident:
        raise ValueError('The manifest selects a different SDK profile. Explicitly update its project binding.')
    raw = sdk_host.invoke(context['runner'], context['paths']['sdk'], 'Profile.ps1',
        ['-Action', 'Resolve', '-Profile', ident, '-ContractRoot', context['paths']['contract'],
         '-LibrariesRoot', context['paths']['libraries']], context['cache'])
    resolved = package.decode(raw)
    if (resolved.get('profile') != ident or resolved.get('hashes') != context['pins']['sdkProfile']['hashes']
            or resolved.get('technical') is not False):
        raise ValueError('The SDK native source/profile resolution is inconsistent.')
    context['pins']['sdkProfile']['id'] = ident
    context['resolvedProfile'] = resolved
    return resolved
