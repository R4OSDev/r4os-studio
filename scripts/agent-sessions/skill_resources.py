"""Actual frozen skill resource paths, with a local per-run directory view."""
from pathlib import Path
from profile import directory
from skill_application import Snapshot


class SkillResources:
    def __init__(self, worker):
        self.worker = worker; self.access = worker.config.get('skillAccess'); self.view = None

    def paths(self, snapshot=None):
        if not self.access or not self.access.get('alias'): return {}
        if self.view is None:
            snapshot = snapshot or Snapshot(self.worker.store.projects)
            self.view = directory(self.worker.store.directory / self.worker.session_id / 'SkillViews' / self.worker.run_id)
            for entry in self.access['entries']:
                root = snapshot.revision(entry, verify_files=True)[0]
                link = self.view / entry['id']
                if link.is_symlink() and link.resolve() == root: continue
                if link.exists() or link.is_symlink(): raise ValueError('The run skill view has a different target.')
                link.symlink_to(root, target_is_directory=True)
        return {'/workspace/' + self.access['alias']: self.view}

    async def close(self):
        if self.view:
            for entry in self.access['entries']:
                link = self.view / entry['id']
                if link.is_symlink(): link.unlink()
            self.view.rmdir(); self.view = None
