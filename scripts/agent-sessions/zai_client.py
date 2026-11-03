"""User-authorized OpenCode subscription wire identity; native provenance stays local."""
import hashlib
import json
from pathlib import Path
from session_store import encode


def freeze(store, sid, provider):
    profile=json.loads((Path(__file__).resolve().parents[2]/'shared/zai-client.json').read_text())
    scope={'ownerType':store.owner_type,'ownerId':store.owner_id,'sessionId':sid,'providerId':provider['id']}
    return {**profile,'sessionId':'ses_'+hashlib.sha256(encode(scope).encode()).hexdigest()}
