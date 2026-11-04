"""The installed Studio worker identity; no model runtime discovery or probe."""
import hashlib
import json
from pathlib import Path


def engine(scope, api=None):
    root = Path(__file__).resolve().parents[2]
    value = {'kind': 'studio', 'toolScope': scope, 'available': True,
             'version': json.loads((root / 'shared/version.json').read_text())['version'],
             'sha256': hashlib.sha256(Path(__file__).with_name('studio_worker.py').read_bytes()).hexdigest()}
    if api: value['api'] = dict(api)
    return value
