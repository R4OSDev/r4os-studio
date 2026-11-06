"""Read and validate a future Studio selection without starting model work."""
import json
from types import SimpleNamespace

from conversation import Conversation
from session_store import identity
from store import ProjectFault
from studio_engine import model_route as route


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
    return validate_records(store, sid, result)


def context_messages(store, sid):
    from active_history import ActiveHistory
    return ActiveHistory(store, sid).read(('model-selection',))[0]


class RunConfigs:
    """Worker-local immutable accepted selections, bounded by count and bytes."""
    def __init__(self):
        from collections import OrderedDict
        self.values = OrderedDict(); self.bytes = 0

    def get(self, store, sid, rid):
        from run_store import get_run
        if rid in self.values:
            self.values.move_to_end(rid)
            return self.values[rid][0]
        row = get_run(store, rid)
        if row['session_id'] != sid: raise ProjectFault('The original context belongs to another session.', 409)
        raw = row['config']; value = json.loads(raw); size = len(raw.encode())
        if size <= 8*1024*1024:
            while self.values and (len(self.values) >= 128 or self.bytes+size > 8*1024*1024):
                _, (_, old_size) = self.values.popitem(last=False); self.bytes -= old_size
            self.values[rid] = (value, size); self.bytes += size
        return value


def validate_records(store, sid, result, configs=None):
    # Original origins remain immutable. Join full route facts from each
    # accepted run before exposing provider-private history to any connector.
    configs = configs if configs is not None else RunConfigs()
    for record in result:
        config = configs.get(store, sid, record['runId']); origin = record['origin']; selection = origin.get('selection', {})
        if any(selection.get(k) != config.get(k) for k in ('providerId','model','effort','revision')):
            raise ProjectFault('An original context selection disagrees with its accepted run.', 409)
        if config.get('apiProvider'):
            provider = config['apiProvider']
            selection = {**selection, 'connection': {k: provider[k] for k in ('id','kind','baseUrl','protocol','revision','credentialRevision') if k in provider}}
            record['origin'] = {**origin, 'selection': selection}
    return result


def validate_context(store, sid, messages, selection):
    from model_transport import ModelFault, ModelTransport
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
    from studio_history import recoveries
    transport.history_resolver = lambda messages: recoveries(store, sid, messages)
    try: transport.prepare(messages, '', [], selection['effort'])
    except ModelFault as error:
        reasons = {'model_context_unconfirmed_tool': 'An active historical tool observation still lacks a verified original recovery.',
                   'model_context_unpaired': 'The active context contains an unmatched tool call or result.',
                   'model_context_not_portable': 'Original provider content cannot be safely projected to this model.',
                   'model_content_unavailable': 'The active context contains content unavailable to this model.'}
        reason = reasons.get(error.code, 'Local request preparation failed (' + error.code + ').')
        raise ProjectFault('The selected model cannot continue this original context: ' + reason + ' No model request was sent.', 409) from None
    except ProjectFault as error: raise ProjectFault('The selected model cannot continue this original context: '+str(error), 409) from None


def change(store, sid, providers, value):
    from message_store import exists, OPEN
    if exists(store) and store.db.execute('SELECT 1 FROM session_messages WHERE session_id=? AND state IN (?,?,?,?)', (sid, *OPEN)).fetchone():
        raise ProjectFault('Finish, cancel or resolve the original queued input before changing its model connection.', 409)
    from tool_receipt_boundary import require as require_tool_receipts
    require_tool_receipts(store,sid,'Resolve the original tool receipt before changing its model connection.')
    selection = target(store, sid, providers, value)
    validate_context(store, sid, context_messages(store, sid), selection)
    return selection['engine']
