"""Coordinator-only import context; no Worker import or provider inference."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROBE = r'''
import asyncio
import json
import os
import sys
from types import SimpleNamespace
import uuid

sys.path.insert(0, sys.argv[1])
from goal_control import live_control
from attachment_store import birth
from store import ProjectFault
assert 'lease' not in sys.modules
assert not any(path.endswith('/project-development') for path in sys.path)

async def main():
    run_id, session_id, request_id = [str(uuid.uuid4()) for _ in range(3)]
    identity = {'pid': os.getpid(), 'birth': birth(os.getpid())}
    row = {'id': run_id, 'worker': json.dumps(identity)}
    store = SimpleNamespace(db=SimpleNamespace(execute=lambda *args:
        SimpleNamespace(fetchone=lambda: row)))
    commands = []
    async def worker(reader, writer):
        try:
            data = await reader.readline()
            if data:
                command = json.loads(data)
                assert command == {'runId': run_id, 'sessionId': session_id, 'requestId': request_id}
                commands.append(command)
                writer.write((json.dumps({'result': {'requestId': request_id, 'state': 'confirmed'}}) + '\n').encode())
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
    server = await asyncio.start_unix_server(worker, path='\0r4os-studio-goal-' + run_id)
    try:
        receipt = await live_control(store, session_id, request_id)
        assert receipt == {'requestId': request_id, 'state': 'confirmed'}
        row['worker'] = json.dumps({**identity, 'birth': 'foreign-generation'})
        try:
            await live_control(store, session_id, request_id)
        except ProjectFault as error:
            assert error.code == 403
        else:
            raise AssertionError('A foreign worker generation was accepted')
        assert len(commands) == 1
        assert 'lease' not in sys.modules
    finally:
        server.close()
        await server.wait_closed()

asyncio.run(main())
'''


class HostOnlyGoalControlTests(unittest.TestCase):
    def test_live_command_works_without_development_imports_and_preserves_worker_identity_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-B', '-c', PROBE, str(Path(__file__).resolve().parent)],
                cwd=directory, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
