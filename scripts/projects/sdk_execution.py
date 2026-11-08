"""SDK-selected source maintenance in a private offline namespace."""
import json
import os
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from workspace_context import Workspace
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
    context_paths = {'/' + name: path for name, path in context['paths'].items()}
    context_paths.update({'/cache': directory, '/powershell': context['runner'].parent})
    working = Workspace(workspace, context_paths)
    bins = [context['runner'].parent, context['paths']['zig']]
    if context.get('rust'): bins.append(context['rust']['prefix'] / context['rust']['compiler'].parent)
    command = working.command(working.arguments(arguments), environment={'HOME': directory / 'home',
        'PATH': ':'.join(map(str, [*bins, '/usr/bin', '/bin'])), 'CARGO_HOME': directory / 'cargo',
        'RUSTUP_AUTO_INSTALL': '0', 'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT': '1', 'POWERSHELL_TELEMETRY_OPTOUT': '1'})
    stdout, stderr = directory / (label + '.stdout'), directory / (label + '.stderr')
    # Bound streams while reading them. RLIMIT_FSIZE would also limit .NET's
    # anonymous backing files and can prevent PowerShell from starting.
    with stdout.open('wb') as out, stderr.open('wb') as err:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
