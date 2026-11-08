"""Per-process working paths and environment for direct host execution."""
import json
from pathlib import Path


class Workspace:
    def __init__(self, workspace, paths=None):
        self.workspace = Path(workspace).resolve()
        self.paths = {'/workspace': self.workspace,
                      **{str(key).rstrip('/'): Path(value).absolute() for key, value in (paths or {}).items()}}

    def path(self, value='.'):
        value = str(value)
        for alias, target in sorted(self.paths.items(), key=lambda item: -len(item[0])):
            if value == alias or value.startswith(alias + '/'):
                return target / value[len(alias):].lstrip('/')
        selected = Path(value)
        return selected if selected.is_absolute() else self.workspace / selected

    def arguments(self, arguments):
        # Only internal structured argv paths are translated. Shell source and
        # user command text are never rewritten.
        result = []
        for argument in map(str, arguments):
            if argument.startswith('/'):
                argument = str(self.path(argument))
            elif '=' in argument:
                key, value = argument.split('=', 1)
                if value.startswith('/'): argument = key + '=' + str(self.path(value))
            result.append(argument)
        return result

    def command(self, arguments, workdir='.', environment=None):
        values = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                  'STUDIO_WORKSPACE': str(self.workspace),
                  'STUDIO_PATHS': json.dumps({key: str(value) for key, value in self.paths.items()})}
        values.update({key: str(value) for key, value in (environment or {}).items()})
        return ['/usr/bin/env', '-i', '-C', str(self.path(workdir)),
                *(key + '=' + value for key, value in values.items()), *map(str, arguments)]
