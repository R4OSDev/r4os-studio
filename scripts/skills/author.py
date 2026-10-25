#!/usr/bin/env python3
"""Fixed author validation/publication broker; never mounted in the tool sandbox."""
from contextlib import closing
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import uuid

spec = importlib.util.spec_from_file_location('skill_package_store', Path(__file__).with_name('store.py'))
packages = importlib.util.module_from_spec(spec); spec.loader.exec_module(packages)


class AuthorLease:
    def __init__(self, projects, skill_id, session_id, run_id, fd, tool):
        self.projects = packages.folder(projects); self.skill_id = packages.identity(skill_id)
        self.session_id, self.run_id = packages.identity(session_id), packages.identity(run_id)
        self.fd = fd; self.tool = tool

    def verify(self, root, ident):
        if root != self.projects.parent / 'Skills' or ident != self.skill_id:
            raise packages.SkillFault('This author tool belongs to another skill.', 403)
        catalog = root / 'Skills.sqlite'
        if catalog.resolve(strict=True) != catalog or not stat.S_ISREG(catalog.stat().st_mode):
            raise packages.SkillFault('The existing skill catalog is unavailable.', 503)
        lock = packages.folder(root / '.locks') / ident
        info, held = lock.lstat(), os.fstat(self.fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != (held.st_dev, held.st_ino)):
            raise packages.SkillFault('The skill workspace lease changed.', 403)
        try: fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise packages.SkillFault('Another operation holds the skill workspace.', 409) from None
        path = packages.folder(root / ident / 'Sessions') / 'Sessions.sqlite'
        if path.resolve(strict=True) != path or not stat.S_ISREG(path.stat().st_mode):
            raise packages.SkillFault('Author session storage is unavailable.', 503)
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            row = db.execute('''SELECT r.state,r.busy,r.config,r.worker,s.revision FROM runs r
                JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND s.id=? AND s.project_id=?''',
                (self.run_id, self.session_id, ident)).fetchone()
        if not row or row[0] not in ('starting', 'running') or row[1] != 1:
            raise packages.SkillFault('The author run is no longer accepting tool effects.', 409)
        config, worker = json.loads(row[2]), json.loads(row[3] or '{}')
        parent = os.getppid()
        birth = (Path('/proc') / str(parent) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]
        if (config.get('owner') != {'type': 'skill', 'id': ident} or config.get('engine', {}).get('profile') != 'studio-skill-tools-v2'
                or config.get('revision') != row[4] or config.get('permissions', {}).get('studio.' + self.tool) is not True
                or worker.get('pid') != parent or worker.get('birth') != birth):
            raise packages.SkillFault('The author tool permission or worker binding changed.', 403)


def main():
    os.umask(0o077)
    if len(sys.argv) != 8: raise packages.SkillFault('Invalid author tool binding.', 400)
    projects = Path(sys.argv[1]).absolute(); ident, session, run, fd, tool, node = sys.argv[2:8]
    if tool not in ('validate_skill', 'save_skill'): raise packages.SkillFault('Unknown author operation.', 400)
    raw = sys.stdin.buffer.read(8193)
    if len(raw) > 8192: raise packages.SkillFault('Author request exceeds its limit.', 400)
    data = json.loads(raw)
    if not isinstance(data, dict): raise packages.SkillFault('Unexpected author tool fields.', 400)
    expected = {'revision', 'draftHash', 'callId'} if tool == 'save_skill' else set(data) & {'expectedDraftHash'}
    if set(data) != expected: raise packages.SkillFault('Unexpected author tool fields.', 400)
    root = projects.parent / 'Skills'; lease = AuthorLease(projects, ident, session, run, int(fd), tool)
    lease.verify(root, ident)
    with closing(packages.connect(root)) as db:
        if tool == 'save_skill':
            if not isinstance(data['callId'], str) or not 1 <= len(data['callId']) <= 256:
                raise packages.SkillFault('Invalid author call receipt.', 400)
            request = {key: data[key] for key in ('revision', 'draftHash')}
            request.update(id=ident, requestId=str(uuid.uuid5(uuid.UUID(run), 'skill-save:' + data['callId'])))
            result = packages.publish(db, root, request, node, author=lease)
        else:
            with packages.locked(root, ident, lease):
                current = packages.detail(db, root, ident)
                expected_hash = data.get('expectedDraftHash')
                if expected_hash is not None and (not isinstance(expected_hash, str) or not re.fullmatch('[a-f0-9]{64}', expected_hash)
                        or current['draftHash'] != expected_hash):
                    raise packages.SkillFault('The skill draft changed. Validate its current files.', 409)
                files, contents, tree_hash = packages.inventory(root / ident / 'Workspace')
                result = {**current, 'validation': packages.validate(files, contents, tree_hash, node)}
                lease.verify(root, ident)
    print(json.dumps({'result': result}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except packages.SkillFault as error:
        print(json.dumps({'error': str(error), 'code': error.code})); sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'The author tool could not confirm its result. Existing data was preserved.', 'code': 503})); sys.exit(1)
