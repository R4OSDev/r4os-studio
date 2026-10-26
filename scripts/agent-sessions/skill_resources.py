"""Virtual read-only paths through existing file-tool arguments, without workspace copies."""
import asyncio
import json
from pathlib import Path
import shutil
from file_worker import parts, Fault
from profile import directory
from session_store import encode
from skill_application import revision


class SkillResources:
    def __init__(self, worker):
        self.worker = worker; self.access = worker.config.get('skillAccess'); self.view = None

    def target(self, path):
        if not self.access or not self.access.get('alias'): return None
        names = parts(path)
        return names[1:] if names and names[0] == self.access['alias'] else None

    def patch_target(self, patch):
        for line in patch.splitlines():
            for prefix in ('*** Add File: ', '*** Update File: ', '*** Delete File: ', '*** Move to: '):
                if line.startswith(prefix) and self.target(line[len(prefix):]) is not None: return True
        return False

    async def read(self, name, arguments, relative):
        if name not in ('read_file', 'list_directory', 'search'):
            return {'success': False, 'error': 'readOnly', 'output': 'Published skill resources are read-only. Edit the selected skill draft in Skill Manager.'}
        from store import ProjectFault
        try:
            if self.access.get('schema') != 1: raise ValueError()
            collision = self.worker.store.workspace / self.access['alias']
            if collision.exists() or collision.is_symlink():
                return {'success': False, 'error': 'conflict', 'output': 'A workspace entry now conflicts with this run\'s virtual skill path. Its contents were preserved.'}
            entries = self.access['entries']; ids = {entry['id'] for entry in entries}
            if relative and relative[0] not in ids:
                return {'success': False, 'error': 'unavailable', 'output': 'This skill is not enabled in the current run.'}
            roots = [(entry['id'], revision(self.worker.store.projects, entry, verify_files=True)[0]) for entry in entries]
            if self.view is None:
                candidate = directory(self.worker.store.directory / self.worker.session_id / 'SkillViews' / self.worker.run_id)
                if any(path.name not in ids or not path.is_dir() or path.is_symlink() or any(path.iterdir()) for path in candidate.iterdir()):
                    raise ValueError()
                self.view = candidate
                for ident in ids: directory(self.view / ident)
            args = ['/usr/bin/bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts']
            for path in ('/usr', '/lib', '/lib64'):
                if Path(path).exists(): args += ['--ro-bind', path, path]
            args += ['--symlink', '/usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
                '--dir', '/runner', '--ro-bind', str(Path(__file__).with_name('file_worker.py')), '/runner/file_worker.py',
                '--ro-bind', str(self.view), '/workspace']
            for ident, root in roots: args += ['--ro-bind', str(root), '/workspace/' + ident]
            args += ['--chdir', '/workspace', '--clearenv', '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PATH', '/usr/bin:/bin',
                     '/usr/bin/python3', '-I', '-B', '/runner/file_worker.py']
            value = {**arguments, 'root': 'workspace', 'path': '/'.join(relative) or '.'}
            process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, limit=262144)
            try:
                raw, _ = await asyncio.wait_for(process.communicate(encode({'tool': name, 'arguments': value}).encode()), 30)
                if process.returncode or len(raw) > 196608: raise ValueError()
                result = json.loads(raw)
                if name == 'read_file' and result.get('success'):
                    expected = next((file['sha256'] for entry in entries if entry['id'] == relative[0]
                                     for file in entry['files'] if file['path'] == '/'.join(relative[1:])), None)
                    if result.get('sha256') != expected: raise ValueError()
                if result.get('success'):
                    result['skillResources'] = [{'id': entry['id'], 'hash': entry['activeHash']} for entry in entries
                                                if not relative or entry['id'] == relative[0]]
                return result
            finally:
                if process.returncode is None: process.kill(); await process.wait()
        except (OSError, ValueError, KeyError, TypeError, ProjectFault, Fault):
            return {'success': False, 'error': 'skillUnavailable', 'output': 'The frozen skill resources are unavailable or changed. Existing data was preserved.'}

    async def close(self):
        if self.view:
            # The model never mounts this parent or the directory entries writable.
            if self.view.resolve(strict=True) != self.view: return
            ids = {entry['id'] for entry in self.access['entries']}
            if any(path.name not in ids or not path.is_dir() or path.is_symlink() or any(path.iterdir()) for path in self.view.iterdir()): return
            shutil.rmtree(self.view); self.view = None
