"""Read and validate a future Studio selection without starting model work."""
import json
from types import SimpleNamespace

from conversation import Conversation
from session_store import identity
from store import ProjectFault


def route(provider):
    return {**{k: provider[k] for k in ('kind','baseUrl','protocol','server')}, 'providerId': provider['id']}


def route_changed(engine, providers, provider_id):
    from api_provider_store import ApiProviders
    try: provider = ApiProviders(providers).get(provider_id)
    except ProjectFault as error:
        if error.code == 404: return False  # Preserve existing name-only edits.
        raise
    return engine.get('api') != route(provider)


def target(store, sid, providers, data):
    from api_provider_store import ApiProviders
    from api_models import freeze_studio
    from studio_engine import engine
    provider = ApiProviders(providers).get(identity(data.get('providerId')))
    if not provider['enabled']: raise ProjectFault('Connect the selected direct model provider first.', 409)
    if not isinstance(data.get('model'), str) or not isinstance(data.get('effort'), str): raise ProjectFault('Choose a model and reasoning level.', 400)
    value = {'providerId': provider['id'], 'model': data['model'], 'effort': data['effort'], 'engine': engine(store.owner_type, route(provider))}
    freeze_studio(store, sid, {'requestId': sid}, providers, value, provider)
    value.pop('apiRunId', None)
    return value


def records(store, sid):
    conversation = Conversation(store, sid)
    if conversation.metadata() is None: raise ProjectFault('This session needs an explicit common history conversion.', 409)
    result = []; cursor = 0
    while page := conversation.records(after=cursor, limit=200):
        result.extend(page); cursor = page[-1]['sequence']
    # Old records keep their original serialized origin. Read full route facts
    # from their immutable accepted run so an edited URL/key cannot receive
    # another route's encrypted/signed provider payload under the same UUID.
    from run_store import get_run
    configs = {}
    for record in result:
        rid = record['runId']
        if rid not in configs: configs[rid] = json.loads(get_run(store, rid)['config'])
        config = configs[rid]; origin = record['origin']; selection = origin.get('selection', {})
        if any(selection.get(k) != config.get(k) for k in ('providerId','model','effort','revision')):
            raise ProjectFault('An original context selection disagrees with its accepted run.', 409)
        if config.get('apiProvider'):
            provider = config['apiProvider']
            selection = {**selection, 'connection': {k: provider[k] for k in ('id','kind','baseUrl','protocol','revision','credentialRevision') if k in provider}}
            record['origin'] = {**origin, 'selection': selection}
    return result


def validate_context(store, sid, messages, selection):
    from model_transport import ModelTransport
    from studio_media import Media
    from profile import regular
    worker = SimpleNamespace(store=store, session_id=sid, config=selection)
    model = selection['apiModel']
    transport = ModelTransport({**selection['apiProvider'], **model, **model.get('messages', {})}, selection['model'],
        chat_policy=selection.get('apiChat'), client=selection.get('apiZaiClient'))
    def media(reference):
        # The generated-image reader creates its folder during regular work;
        # settings/review only resolve existing private original bytes.
        if reference.startswith('studio-generated-image:'):
            regular(store.directory/sid/'GeneratedImages'/(identity(reference.split(':', 1)[1])+'.image'))
        return Media(worker).resolve(reference)
    transport.media_resolver = media
    try: transport.prepare(messages, '', [], selection['effort'])
    except ProjectFault as error: raise ProjectFault('The selected model cannot continue this original context: '+str(error), 409) from None


def change(store, sid, providers, value):
    from message_store import exists, OPEN
    if exists(store) and store.db.execute('SELECT 1 FROM session_messages WHERE session_id=? AND state IN (?,?,?,?)', (sid, *OPEN)).fetchone():
        raise ProjectFault('Finish, cancel or resolve the original queued input before changing its model connection.', 409)
    if store.db.execute("SELECT 1 FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND (t.state='unknown' OR t.result IS NULL)", (sid,)).fetchone():
        raise ProjectFault('Resolve the original tool receipt before changing its model connection.', 409)
    selection = target(store, sid, providers, value)
    validate_context(store, sid, records(store, sid), selection)
    return selection['engine']
