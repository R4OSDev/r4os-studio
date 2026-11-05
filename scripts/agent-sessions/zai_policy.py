"""Z.AI Coding Plan product boundary; never the prepaid general API."""
from store import ProjectFault

KIND = 'zai-coding-plan'
BASE_URL = 'https://api.z.ai/api/coding/paas/v4'
MESSAGES_URL = 'https://api.z.ai/api/anthropic/v1'
ENDPOINTS = {'chat-completions': BASE_URL, 'messages': MESSAGES_URL}


def require(value):
    if (value.get('kind') != KIND or value.get('protocol') not in ENDPOINTS
            or value.get('baseUrl') != ENDPOINTS[value['protocol']] or value.get('auth') != 'bearer'
            or value.get('server', 'custom') != 'custom' or 'openrouter' in value):
        raise ProjectFault('Z.AI Coding Plan requires its matching subscription endpoint, Chat Completions or Messages and its own API key. No paid API fallback is available.', 400)
