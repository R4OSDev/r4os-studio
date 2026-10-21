import json
import tempfile
import unittest
import uuid
from pathlib import Path
from layout import migrate, workspace
from store import ProjectFault


class LayoutTests(unittest.TestCase):
    def test_migration_preserves_sources_and_recovers_both_directions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); ident = str(uuid.uuid4()); project = root / ident
            (project / 'src').mkdir(parents=True)
            (project / 'module.R4MF').write_text('manifest')
            source = project / 'src/main.c'; source.write_text('user changes')
            inode = source.stat().st_ino
            self.assertEqual(workspace(root, ident), project)
            self.assertEqual(migrate(root, ident)['layout'], 2)
            current = workspace(root, ident, True)
            self.assertEqual((current / 'src/main.c').stat().st_ino, inode)
            self.assertEqual((current / 'src/main.c').read_text(), 'user changes')
            self.assertEqual(migrate(root, ident)['layout'], 2)
            # Resume forward publication after a crash before the directory rename.
            journal = root / '.studio/layouts' / (ident + '.json')
            data = json.loads(journal.read_text()); data['phase'] = 'moving'
            journal.write_text(json.dumps(data))
            current.rename(project / '.workspace-migration')
            self.assertEqual(migrate(root, ident)['layout'], 2)
            # Recreate a crash halfway through the explicit rollback.
            journal = root / '.studio/layouts' / (ident + '.json')
            data = json.loads(journal.read_text()); data['phase'] = 'rollingBack'
            journal.write_text(json.dumps(data))
            (current / 'module.R4MF').rename(project / 'module.R4MF')
            self.assertEqual(migrate(root, ident, True)['layout'], 1)
            self.assertEqual(source.stat().st_ino, inode)
            self.assertEqual(source.read_text(), 'user changes')

    def test_conflicts_and_changed_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); ident = str(uuid.uuid4()); project = root / ident
            project.mkdir(); (project / 'module.R4MF').write_text('original')
            (project / 'Workspace').write_text('foreign')
            with self.assertRaises((ProjectFault, FileExistsError)): migrate(root, ident)
            self.assertEqual((project / 'Workspace').read_text(), 'foreign')
            (project / 'Workspace').unlink()
            migrate(root, ident)
            manifest = project / 'Workspace/module.R4MF'; manifest.write_text('new user changes')
            with self.assertRaises(ProjectFault): migrate(root, ident, True)
            self.assertEqual(manifest.read_text(), 'new user changes')


if __name__ == '__main__': unittest.main()
