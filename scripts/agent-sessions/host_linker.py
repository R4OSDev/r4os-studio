"""Report the host C driver used by ordinary host compilation."""
import shutil


def qualify():
    target = shutil.which('cc')
    return {'available': target is not None, 'target': target,
            'code': None if target else 'missing',
            'reason': None if target else 'Host C linker unavailable: cc is not on PATH.'}
