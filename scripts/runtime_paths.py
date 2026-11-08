"""Relocate old managed program entrypoints without altering installed bytes."""
from pathlib import Path
import shlex


def launchers(root, directory):
    root = Path(root).resolve(); directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    replacements = {}; bins = []
    for relative in ('Programs/Bin', 'Programs/Python/bin', 'Programs/Pwndbg/bin'):
        source = root / relative
        if not source.is_dir(): continue
        target = directory / relative.replace('/', '-')
        target.mkdir(exist_ok=True, mode=0o700); bins.append(str(target))
        for path in source.iterdir():
            if not path.is_file() or path.stat().st_size > 65536: continue
            raw = path.read_bytes()
            if not raw.startswith(b'#!'): continue
            text = raw.decode('utf-8', 'replace'); first = text.splitlines()[0]
            arguments = None
            if relative in ('Programs/Python/bin', 'Programs/Pwndbg/bin') and ('python' in first.lower() or text.startswith("#!/bin/sh\n'''exec'")):
                arguments = [str(source / 'python'), str(path)]
            elif first.startswith('#!/runtime/') and 'python' in first:
                arguments = [str(root / first[2:].removeprefix('/runtime/')), str(path)]
            elif first.startswith('#!') and '/.stage-' in first and 'python' in first:
                # Native venv entrypoints from a staged recipe remain executable
                # after its directory is published at the final runtime path.
                arguments = [str(source / Path(first[2:]).name), str(path)]
            elif relative == 'Programs/Bin' and text.startswith('#!/bin/sh\nset -eu\nexec /runtime/'):
                words = shlex.split(text.splitlines()[2])
                if words[0] == 'exec' and words[-1] == '$@':
                    arguments = [str(root / word.removeprefix('/runtime/')) if word.startswith('/runtime/') else word for word in words[1:-1]]
            if arguments is None: continue
            data = ('#!/usr/bin/python3\nimport os,sys\ncommand=' + repr(arguments) + '\nos.execv(command[0],[*command,*sys.argv[1:]])\n').encode()
            entry = target / path.name
            if not entry.exists() or entry.read_bytes() != data:
                entry.write_bytes(data); entry.chmod(0o700)
            replacements[str(path)] = str(entry)
    return replacements, bins
