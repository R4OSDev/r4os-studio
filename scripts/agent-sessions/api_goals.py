"""Native API Goal metadata controls without credentials or model transport."""
import copy
import json
from pathlib import Path

from profile import CODEX_SHA256,CODEX_VERSION,PROFILE,prepare
from store import ProjectFault


def qualified(engine):
    return (isinstance(engine.get('api'),dict) and engine.get('version')==CODEX_VERSION
        and engine.get('sha256')==CODEX_SHA256)


def require(engine):
    if not qualified(engine):
        raise ProjectFault('This API session has no qualified native Goal runtime. Its existing conversation was preserved.',409)


def metadata_arguments(store,sid,providers,new_thread=False):
    """Only paused metadata commands may use this isolated launch profile.

    No key is claimed/read and no inference relay is created. A new persistent
    thread needs current public model facts. Existing paused controls can use
    their original native catalog even when the connection is disconnected.
    """
    session=store.get(sid);engine=session['engine'];require(engine)
    state=store.directory/sid/'Codex';catalogue=None
    if new_thread:
        from api_models import catalog,connection
        provider=connection(providers,session['providerId']);selected=engine['api']
        if (not provider or not provider['enabled'] or selected['providerId']!=provider['id']
            or selected['baseUrl']!=provider['baseUrl'] or selected['protocol']!=provider['protocol']
            or selected.get('server','custom')!=provider.get('server','custom')):
            raise ProjectFault('The original API connection is unavailable or changed. No Goal thread was created.',409)
        model=next((value for value in catalog(providers,provider) if value['slug']==session['model']),None)
        if model is None:raise ProjectFault('Refresh the selected API model facts before saving this first Goal.',409)
        model=copy.deepcopy(model);model.pop('studio_chat',None);catalogue={'models':[model]}
    elif not (state/'models.json').is_file():
        raise ProjectFault('The original native catalog is unavailable. Existing Goal data was preserved.',503)
    args,_=prepare(Path(store.r4os)/'Toolchains/Codex'/engine['version']/'codex',state/'ApiHome',state,
        json.loads((Path(__file__).parent/'features.json').read_text()),
        session['model'] if new_thread else None,session['providerId'] if new_thread else None,
        selected_profile=engine.get('profile',PROFILE),goals_enabled=True,catalog_data=catalogue)
    args.insert(1,'--unshare-net')
    from api_runtime import provider_name
    provider=provider_name(session['providerId'])
    # Stable native provider identity, but a fixed unreachable endpoint inside
    # a private network namespace. Metadata must never acquire an inference path.
    settings={'name':'Studio API','base_url':'http://127.0.0.1:9/v1','wire_api':'responses',
        'requires_openai_auth':False,'supports_websockets':False,'supports_standalone_web_search':False,
        'request_max_retries':0,'stream_max_retries':0}
    pairs=','.join(key+'='+json.dumps(value,separators=(',',':')) for key,value in settings.items())
    return args+['-c','model_provider='+json.dumps(provider),'-c','model_providers.'+provider+'={'+pairs+'}']
