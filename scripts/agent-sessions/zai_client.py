"""User-authorized OpenCode subscription wire identity; native provenance stays local."""
import hashlib
import json
import re
from pathlib import Path
from session_store import encode


def freeze(store, sid, provider):
    profile=json.loads((Path(__file__).resolve().parents[2]/'shared/zai-client.json').read_text())
    scope={'ownerType':store.owner_type,'ownerId':store.owner_id,'sessionId':sid,'providerId':provider['id']}
    return {**profile,'sessionId':'ses_'+hashlib.sha256(encode(scope).encode()).hexdigest()}


def headers(client):
    from model_transport import ModelFault
    if (not isinstance(client, dict) or client.get('schema') != 1
            or not re.fullmatch(r'\d+\.\d+\.\d+', client.get('referenceVersion', ''))
            or not re.fullmatch(r'[a-f0-9]{40}', client.get('referenceCommit', ''))
            or client.get('userAgent') != 'opencode/' + client['referenceVersion']
            or not re.fullmatch(r'ses_[a-f0-9]{64}', client.get('sessionId', ''))):
        raise ModelFault('model_client_identity_unavailable')
    session = client['sessionId']
    return {'User-Agent': client['userAgent'], 'x-opencode-session-id': session,
            'x-session-affinity': session, 'X-Session-Id': session}
