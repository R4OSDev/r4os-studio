"""SDK-selected source maintenance in a private offline namespace."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time

from layout import folder, save
from store import ProjectFault


def run(context, workspace, directory, arguments, label):
    directory = Path(directory).absolute()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = folder(directory)
    for name in ('home', 'cargo'):
        (directory / name).mkdir(mode=0o700, exist_ok=True)
        folder(directory / name)
    command = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts']
    for name in ('/usr', '/lib', '/lib64'):
        if Path(name).exists():
            command += ['--ro-bind', name, name]
    command += ['--symlink', '/usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                '--dir', '/etc', '--dir', '/home', '--bind', str(workspace), '/workspace', '--bind', str(directory), '/cache']
    for name in ('passwd', 'group', 'nsswitch.conf', 'os-release'):
        command += ['--ro-bind', '/etc/' + name, '/etc/' + name]
    for name, path in context['paths'].items():
        command += ['--ro-bind', str(path), '/' + name]
    command += ['--ro-bind', str(context['runner'].parent), '/powershell']
    rust_bin = ''
    if context.get('rust'):
        rust_bin = '/install/' + str(context['rust']['compiler'].relative_to('Install').parent)
    command += ['--chdir', '/workspace', '--clearenv', '--setenv', 'HOME', '/cache/home',
                '--setenv', 'PATH', ':'.join(name for name in ('/powershell', '/zig', rust_bin, '/usr/bin', '/bin') if name),
                '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'CARGO_HOME', '/cache/cargo',
                '--setenv', 'CARGO_NET_OFFLINE', 'true', '--setenv', 'RUSTUP_AUTO_INSTALL', '0',
                '--setenv', 'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT', '1', '--setenv', 'POWERSHELL_TELEMETRY_OPTOUT', '1']
    stdout, stderr = directory / (label + '.stdout'), directory / (label + '.stderr')
    # Bound streams while reading them. RLIMIT_FSIZE would also limit .NET's
    # anonymous backing files and can prevent PowerShell from starting.
    with stdout.open('wb') as out, stderr.open('wb') as err:
        process = subprocess.Popen([*command, *map(str, arguments)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        selector = selectors.DefaultSelector(); total = 0; deadline = time.monotonic() + 120
        try:
            selector.register(process.stdout, selectors.EVENT_READ, out)
            selector.register(process.stderr, selectors.EVENT_READ, err)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise ProjectFault('SDK source synchronization exceeded its time limit.', 409)
                for key, _ in selector.select(1):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(block)
                    if total > 2 * 1024**2:
                        raise ProjectFault('SDK source synchronization exceeded its diagnostic limit.', 409)
                    key.data.write(block)
            code = process.wait(timeout=max(.1, deadline - time.monotonic()))
        finally:
            selector.close()
            if process.poll() is None:
                process.kill(); process.wait()
            process.stdout.close(); process.stderr.close()
    receipt = {'schema': 1, 'arguments': list(map(str, arguments)), 'exitCode': code,
               'sdkProfile': context['pins']['sdkProfile']}
    save(directory / (label + '.json'), receipt)
    if code:
        raise ProjectFault('The SDK could not synchronize the project inputs. Its original diagnostics were preserved.', 409)
    return receipt
