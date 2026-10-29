"""Qualify the existing public host cc without exposing host /etc."""
import os
from pathlib import Path
import stat

ENTRY = Path('/usr/bin/cc')
ALTERNATIVE = Path('/etc/alternatives/cc')
REASONS = {
    'missing': 'the host cc entry or one of its targets is missing',
    'cycle': 'the host cc symlink chain contains a cycle',
    'outside_public_tools': 'the host cc target leaves the allowed public /usr tool tree',
    'unsupported_path': 'the host cc path uses an unsupported directory alias',
    'non_executable': 'the host cc target is not a regular executable',
    'chain_limit': 'the host cc symlink chain exceeds the supported bound',
    'unavailable': 'the host cc path cannot be qualified',
}


def qualify(entry=ENTRY, alternative=ALTERNATIVE, public=Path('/usr')):
    try:
        if public.resolve(strict=True) != public.absolute(): raise ValueError('unsupported_path')
        current = entry; seen = set()
        for _ in range(16):
            if current in seen: raise ValueError('cycle')
            if current != alternative and not current.is_relative_to(public): raise ValueError('outside_public_tools')
            if current.parent.resolve(strict=True) != current.parent: raise ValueError('unsupported_path')
            seen.add(current); info = current.lstat()
            if stat.S_ISLNK(info.st_mode):
                target = Path(os.readlink(current))
                current = Path(os.path.normpath(target if target.is_absolute() else current.parent / target))
                continue
            if not current.is_relative_to(public): raise ValueError('outside_public_tools')
            if not stat.S_ISREG(info.st_mode) or not os.access(current, os.X_OK): raise ValueError('non_executable')
            return {'available': True, 'target': str(current), 'code': None, 'reason': None}
        raise ValueError('chain_limit')
    except (OSError, ValueError, RuntimeError) as error:
        code = ('missing' if isinstance(error, FileNotFoundError) else 'cycle' if isinstance(error, RuntimeError)
            else str(error) if isinstance(error, ValueError) and str(error) in REASONS else 'unavailable')
        return {'available': False, 'target': None, 'code': code,
            'reason': 'Host C linker unavailable: ' + REASONS[code] + '. Native R4X build pins are unchanged.'}


def bindings(selection=None):
    value = qualify() if selection is None else selection
    source = value['target'] if value['available'] else str(Path(__file__).with_name('host-cc-unavailable.sh'))
    # Only this one validated public file enters private /etc. A private PATH
    # alias also gives a precise diagnostic when the host cc entry is absent or
    # rejected; a foreign alternative is never mounted or executed.
    return ['--dir', '/etc/alternatives', '--dir', '/host-tools',
        '--ro-bind', source, '/etc/alternatives/cc',
        '--symlink', value['target'] if value['available'] else '/etc/alternatives/cc', '/host-tools/cc']
