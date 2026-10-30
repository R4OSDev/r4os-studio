"""Private API usage provenance, linked to existing stable numeric receipts."""
import json

from api_model_info import model_id
from api_server import server
from profile import CODEX_SHA256
from session_store import identity,encode
from store import ProjectFault


def wire_receipts(store,sid,run_id,receipts):
    """Only the original worker persists its trusted relay's bounded observations."""
    row=store.db.execute('SELECT config FROM runs WHERE id=? AND session_id=?',(identity(run_id),sid)).fetchone()
    if not row or not json.loads(row['config']).get('apiProvider') or len(receipts)>256:
        raise ProjectFault('The original API wire-usage binding is unavailable.',409)
    with store.db:
        store.db.execute('''CREATE TABLE IF NOT EXISTS statistic_api_wire(
            session_id TEXT NOT NULL,run_id TEXT NOT NULL,response_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,usage TEXT NOT NULL,PRIMARY KEY(run_id,response_id))''')
        for receipt in receipts:
            response=receipt['responseId'];usage=receipt['usage'];ordinal=receipt['ordinal']
            if (not isinstance(response,str) or not 1<=len(response.encode())<=256
                    or any(ord(c)<33 or ord(c)==127 or 0xd800<=ord(c)<=0xdfff for c in response)
                    or type(ordinal) is not int or not 1<=ordinal<=256
                    or usage is not None and (not isinstance(usage,dict) or not usage
                        or set(usage)-{'input_tokens','output_tokens','total_tokens','cached_input_tokens','reasoning_output_tokens'}
                        or any(type(v) is not int or not 0<=v<=9007199254740991 for v in usage.values()))):
                raise ProjectFault('The API usage observation is invalid.',409)
            value=(sid,run_id,response,ordinal,encode(usage))
            other=store.db.execute('SELECT response_id FROM statistic_api_wire WHERE run_id=? AND ordinal=?',(run_id,ordinal)).fetchone()
            if other and other[0]!=response:raise ProjectFault('The original API usage request ordinal changed.',409)
            previous=store.db.execute('SELECT * FROM statistic_api_wire WHERE run_id=? AND response_id=?',(run_id,response)).fetchone()
            if previous and tuple(previous)!=value:raise ProjectFault('Conflicting API wire usage was preserved.',409)
            store.db.execute('INSERT OR IGNORE INTO statistic_api_wire VALUES (?,?,?,?,?)',value)


def reported(store,sid,run_id,response):
    selected=json.loads(store.row(sid)['engine']).get('api')
    row=store.db.execute('SELECT config FROM runs WHERE id=? AND session_id=?',(run_id,sid)).fetchone() if run_id else None
    api=bool(selected or row and json.loads(row['config']).get('apiProvider'))
    if not api:return False,None
    has=store.db.execute("SELECT 1 FROM sqlite_master WHERE name='statistic_api_wire'").fetchone()
    wire=store.db.execute('SELECT usage FROM statistic_api_wire WHERE session_id=? AND run_id=? AND response_id=?',
        (sid,run_id,response)).fetchone() if has and row else None
    return True,json.loads(wire[0]) if wire else None


def record(store,sid,key,thread,response,run_id):
    """Never change an existing spend identity or publish provider credentials."""
    if not run_id:return
    row=store.db.execute('SELECT config FROM runs WHERE id=? AND session_id=?',(identity(run_id),sid)).fetchone()
    if not row:return
    config=json.loads(row['config']);binding=config.get('apiProvider')
    if binding is None:return
    selected=config.get('engine',{}).get('api')
    if (not isinstance(binding,dict) or not isinstance(selected,dict)
            or selected.get('providerId')!=binding.get('id') or selected.get('baseUrl')!=binding.get('baseUrl')
            or selected.get('protocol')!=binding.get('protocol')
            or selected.get('server','custom')!=binding.get('server','custom')
            or binding.get('kind') not in ('openrouter','openai-compatible','local')
            or binding.get('protocol') not in ('responses','chat-completions')
            or any(type(binding.get(k)) is not int or binding[k]<minimum for k,minimum in (('revision',1),('credentialRevision',0)))):
        raise ProjectFault('The original API usage provenance is unconfirmed; existing numeric receipts were preserved.',409)
    chat=binding['protocol']=='chat-completions'
    origin={'schema':1,'providerId':identity(binding['id']),'providerKind':binding['kind'],
        'configRevision':binding['revision'],'credentialRevision':binding['credentialRevision'],
        'protocol':binding['protocol'],'server':server(binding.get('server','custom')),
        'adapter':'studio-chat-v1' if chat else 'studio-responses-v1','runtimeSha256':CODEX_SHA256,
        'threadId':thread,'responseId':response,'responseIdKind':'local-transport' if chat else 'provider',
        'requestedModel':model_id(config.get('model'))}
    with store.db:
        store.db.execute('''CREATE TABLE IF NOT EXISTS statistic_api_origins(
            key TEXT PRIMARY KEY,session_id TEXT NOT NULL,run_id TEXT NOT NULL,origin TEXT NOT NULL)''')
        previous=store.db.execute('SELECT * FROM statistic_api_origins WHERE key=?',(key,)).fetchone()
        if previous:
            old=json.loads(previous['origin'])
            # Raw events, retained native records and restore all describe the
            # same original response. Rotation does not make a new receipt.
            stable=set(origin)-{'configRevision','credentialRevision'}
            if previous['session_id']!=sid or any(old.get(k)!=origin[k] for k in stable):
                raise ProjectFault('Conflicting API usage provenance was preserved.',409)
            return
        store.db.execute('INSERT INTO statistic_api_origins VALUES (?,?,?,?)',(key,sid,run_id,encode(origin)))
