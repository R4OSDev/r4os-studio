"""Z.AI Coding Plan product boundary; never the prepaid general API."""
from store import ProjectFault

KIND = 'zai-coding-plan'
BASE_URL = 'https://api.z.ai/api/coding/paas/v4'


def require(value):
    if (value.get('kind') != KIND or value.get('baseUrl') != BASE_URL
            or value.get('protocol') != 'chat-completions' or value.get('auth') != 'bearer'
            or value.get('server', 'custom') != 'custom' or 'openrouter' in value):
        raise ProjectFault('Z.AI Coding Plan requires its fixed subscription endpoint, Chat Completions and its own API key. No paid API fallback is available.', 400)
