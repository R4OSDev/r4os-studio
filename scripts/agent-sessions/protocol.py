"""Agent compatibility ceiling. Old releases are supported rollback targets."""
import json
from pathlib import Path

EXPECTED = {'agentHostProtocol': 1, 'agentWorkerProtocol': 1, 'agentDataSchema': 1}


def release_protocol(root):
    if not (Path(root) / 'scripts/agent-sessions/worker.py').is_file(): raise ValueError('This release has no compatible agent worker.')
    value = json.loads((Path(root) / 'shared/update-host.json').read_text())
    declared = {k: value[k] for k in EXPECTED if k in value}
    if declared and declared != EXPECTED: raise ValueError('This release requires agent host maintenance.')
    return EXPECTED
