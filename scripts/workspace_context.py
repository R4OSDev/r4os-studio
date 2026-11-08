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

    def arguments(self, arguments, *, path_indices=(), path_options=()):
        """Translate only path positions declared by the structured caller."""
        result = list(map(str, arguments))
        positions = set(path_indices)
        positions.update(index + 1 for index, value in enumerate(result[:-1]) if value in path_options)
        for index in positions:
            result[index] = str(self.path(result[index]))
        return result

    def command(self, arguments, workdir='.', environment=None):
        values = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
                  'STUDIO_WORKSPACE': str(self.workspace),
                  'STUDIO_PATHS': json.dumps({key: str(value) for key, value in self.paths.items()})}
        values.update({key: str(value) for key, value in (environment or {}).items()})
        return ['/usr/bin/env', '-i', '-C', str(self.path(workdir)),
                *(key + '=' + value for key, value in values.items()), *map(str, arguments)]
