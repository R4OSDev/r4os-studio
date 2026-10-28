"""Exercise the real build namespace without a compiler or provider invocation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from builder import Builder

class BoardNamespace(unittest.TestCase):
    def test_private_boards_and_browser_auth_are_absent_from_actual_build_namespace(self):
        with tempfile.TemporaryDirectory(prefix='studio-own-board-build-') as temporary:
            base=Path(temporary);private=base/'Projects/own/Boards/Boards.sqlite';private.parent.mkdir(parents=True);private.write_text('Private human Board fixture')
            builder=Builder.__new__(Builder);builder.root=base/'Development/Work/own'
            for name in ('source','output','home','tools','cargo'): (builder.root/name).mkdir(parents=True,exist_ok=True)
            pinned=base/'pinned';(pinned/'global/p').mkdir(parents=True)
            tool=base/'catalog';tool.write_text('Owned unexecuted catalog fixture');builder.inspector=base/'inspector';builder.inspector.write_text('Owned unexecuted inspector fixture')
            cache=base/'cache'
            for name in ('zig','zig-local','rust-build'):(cache/name).mkdir(parents=True)
            builder.context={'cache':pinned,'tool':tool,'paths':{}};builder.cache=SimpleNamespace(root=cache)
            code="import os,json;assert not os.path.exists(%r);assert not os.path.exists('/workspace/../Boards');assert not any('cookie' in key.lower() or 'csrf' in key.lower() for key in os.environ);assert os.readlink('/proc/self/ns/net')!=%r;print(json.dumps({'privateBoardsHidden':True,'browserAuthAbsent':True,'networkNamespaceIsolated':True}))"%(str(private),os.readlink('/proc/self/ns/net'))
            result=subprocess.run(builder.command(['/usr/bin/python3','-I','-c',code]),capture_output=True,timeout=10,env={**os.environ,'STUDIO_BROWSER_COOKIE':'own-never-forward','STUDIO_CSRF':'own-never-forward'})
            self.assertEqual(result.returncode,0,result.stderr.decode());self.assertTrue(json.loads(result.stdout)['privateBoardsHidden']);self.assertTrue(private.exists())

if __name__=='__main__':unittest.main()
