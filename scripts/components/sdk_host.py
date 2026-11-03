"""Verified host prerequisite and native SDK entry points, not SDK policy."""
import json
import os
from pathlib import Path
import subprocess

from sdk_package import decode, regular_bytes, sha256, relative


def powershell(root):
    record = decode(regular_bytes(Path(root) / 'Profiles/sdk-host.json'))
    if record.get('schema') != 1 or record.get('interface') != 'r4os-studio-sdk-host':
        raise ValueError('The verified PowerShell 7 host prerequisite is not configured.')
    base = Path(root) / relative(record['powershell']['path'])
    for name, checksum in record['powershell']['files'].items():
        path = base / relative(name)
        if sha256(regular_bytes(path, 512 * 1024**2)) != checksum:
            raise ValueError('The verified PowerShell host prerequisite changed: ' + name)
    return base / 'pwsh'


def environment(runner, home):
    return {'PATH': str(Path(runner).parent) + ':/usr/bin:/bin', 'HOME': str(home),
            'LANG': 'C.UTF-8', 'POWERSHELL_TELEMETRY_OPTOUT': '1',
            'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT': '1', 'RUSTUP_AUTO_INSTALL': '0'}


def invoke(runner, sdk, name, arguments, home, timeout=600, log=None):
    driver = Path(sdk) / 'Tools' / name
    if driver.resolve(strict=True) != driver.absolute() or not driver.is_file():
        raise ValueError('The SDK driver is missing or indirect.')
    Path(home).mkdir(parents=True, exist_ok=True, mode=0o700)
    command = [str(runner), '-NoLogo', '-NoProfile', '-File', str(driver), *map(str, arguments)]
    result = subprocess.run(command, capture_output=True, env=environment(runner, home),
                            cwd=home, timeout=timeout)
    if log:
        log = Path(log)
        log.with_suffix('.stdout').write_bytes(result.stdout)
        log.with_suffix('.stderr').write_bytes(result.stderr)
        log.with_suffix('.json').write_text(json.dumps({'command': command, 'exitCode': result.returncode}, indent=2) + '\n')
    if result.returncode:
        detail = (result.stderr or result.stdout)[-1800:].decode('utf-8', errors='replace')
        raise ValueError('The SDK ' + name + ' failed: ' + detail)
    return result.stdout


def rust_check(runner, sdk, install, home, log=None):
    raw = invoke(runner, sdk, 'Rust.ps1', ['--root', install, '--profile', 'sdk', 'check'], home, log=log)
    value = decode(raw)
    if value.get('installed') is not True or value.get('profile') != 'sdk':
        raise ValueError('The SDK Rust toolchain is not ready: ' + str(value.get('reason', 'missing receipt')))
    return value
