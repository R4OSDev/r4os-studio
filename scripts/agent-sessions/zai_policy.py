"""Z.AI Coding Plan product boundary; never the prepaid general API."""
import json
from pathlib import Path
from store import ProjectFault

KIND = 'zai-coding-plan'
ENDPOINTS = json.loads((Path(__file__).resolve().parents[2]/'shared/zai-endpoints.json').read_text())
BASE_URL = ENDPOINTS['chat-completions']
MESSAGES_URL = ENDPOINTS['messages']


def require(value):
    if (value.get('kind') != KIND or value.get('protocol') not in ENDPOINTS
            or value.get('baseUrl') != ENDPOINTS[value['protocol']] or value.get('auth') != 'bearer'
            or value.get('server', 'custom') != 'custom' or 'openrouter' in value):
        raise ProjectFault('Z.AI Coding Plan requires its matching subscription endpoint, Chat Completions or Messages and its own API key. No paid API fallback is available.', 400)
