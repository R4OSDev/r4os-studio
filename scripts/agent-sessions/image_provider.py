"""Pinned OpenAI provider policy: an uncertain image POST is never replayed.

Codex 0.163.0 ignores overrides to its built-in OpenAI provider. Use a private
provider ID with the exact built-in authentication/routing/capability defaults,
and zero HTTP or stream retries. Keep it available when Images is OFF so the
same native thread can resume without changing its provider identity.
"""
from profile import IMAGE_PROFILES,IMAGE_SKILL_PROFILE,NOTES_SKILL_PROFILE,CODEX_VERSION

PROVIDER='studio_openai_images'

def selection(profile):
    return {'modelProvider':PROVIDER} if profile in (*IMAGE_PROFILES,IMAGE_SKILL_PROFILE,NOTES_SKILL_PROFILE) else {}

def configuration():
    return ('model_providers.'+PROVIDER+'={name="OpenAI",wire_api="responses",'
        'requires_openai_auth=true,supports_websockets=true,supports_standalone_web_search=true,'
        'include_internal_metadata=true,request_max_retries=0,stream_max_retries=0,'
        'http_headers={version="'+CODEX_VERSION+'"},'
        'env_http_headers={"OpenAI-Organization"="OPENAI_ORGANIZATION","OpenAI-Project"="OPENAI_PROJECT"}}')
