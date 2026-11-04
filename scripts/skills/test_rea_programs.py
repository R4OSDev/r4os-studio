"""Archive boundaries exercised against real zip/tar bytes."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from rea_programs import unpack


class ProgramArchives(unittest.TestCase):
    def test_zip_traversal_and_link_do_not_write_outside(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for index,entry in enumerate(('../canary','/canary','root/link')):
                archive=root/('bad'+str(index)+'.zip')
                with zipfile.ZipFile(archive,'w') as stream:
                    item=zipfile.ZipInfo(entry)
                    if index==2:item.external_attr=0o120777<<16
                    stream.writestr(item,b'../../canary')
                with self.assertRaises(ValueError):unpack(archive,root/('out'+str(index)),'zip')
            self.assertFalse((root/'canary').exists())

    def test_tar_link_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);archive=root/'bad.tar'
            with tarfile.open(archive,'w') as stream:
                item=tarfile.TarInfo('root/link');item.type=tarfile.SYMTYPE;item.linkname='../../outside';stream.addfile(item)
            with self.assertRaises((ValueError,tarfile.FilterError)):unpack(archive,root/'out','tar')
            self.assertFalse((root/'outside').exists())

    def test_archive_preserves_executable_bytes_and_detaches_hardlinks(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);archive=root/'good.tar'
            with tarfile.open(archive,'w') as stream:
                item=tarfile.TarInfo('root/bin/tool');item.size=3;item.mode=0o6755;stream.addfile(item,io.BytesIO(b'abc'))
                item=tarfile.TarInfo('root/bin/copy');item.type=tarfile.LNKTYPE;item.linkname='root/bin/tool';stream.addfile(item)
            unpack(archive,root/'out','tar')
            for n in ('tool','copy'):
                p=root/'out/bin'/n
                self.assertEqual(p.read_bytes(),b'abc');self.assertEqual(p.stat().st_nlink,1)
                self.assertEqual(p.stat().st_mode&0o6000,0)


if __name__=='__main__':unittest.main()
