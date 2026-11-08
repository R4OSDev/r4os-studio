"""Native account reference for the common model worker; no agent execution."""
import base64
import json
import socket
import stat

from api_provider_store import ApiProviders, private, name
from session_store import identity, encode, now
from store import ProjectFault

KIND='codex-subscription'
BASE='https://chatgpt.com/backend-api/codex'


def binding(value):
    if (not isinstance(value,dict) or set(value)!={'generation','accountId','subject'}
            or any(not isinstance(value[k],str) or not 1<=len(value[k])<=512
                or any(not 33<=ord(c)<=126 for c in value[k]) for k in value)):
        raise ProjectFault('The original native OpenAI identity is unavailable.',409)
    identity(value['generation'])
    return value


def reference(value):return 'native:'+base64.urlsafe_b64encode(encode(binding(value)).encode()).decode()


def frozen(providers,provider):
    api=ApiProviders(providers)
    with api.connect() as db:
        row=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',
            (provider['id'],provider['credentialRevision'])).fetchone() if db else None
        try:
            if row is None or not row[0].startswith('native:'):raise ValueError()
            return binding(json.loads(base64.urlsafe_b64decode(row[0][7:])))
        except (ValueError,TypeError):raise ProjectFault('The original native OpenAI account reference is unavailable.',409) from None


def access(providers,ident,expected=None):
    api=ApiProviders(providers);private(api.parent,directory=True);path=api.parent/'.a.sock'
    try:
        info=path.lstat()
        import os
        if not stat.S_ISSOCK(info.st_mode):raise ValueError()
        message={'action':'credential' if expected is not None else 'snapshot','id':identity(ident)}
        if expected is not None:message['binding']=binding(expected)
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(55);client.connect(str(path));client.sendall((encode(message)+'\n').encode())
            raw=b''
            while b'\n' not in raw:
                chunk=client.recv(16384)
                if not chunk:raise ValueError()
                raw+=chunk
                if len(raw)>32768:raise ValueError()
        value=json.loads(raw)
        if 'error' in value:raise ProjectFault(value['error'],value.get('code',503))
        result=value['result'];original=binding(result['binding'])
        if expected is not None and original!=expected:raise ValueError()
        if result.get('managedRouting') is not False:raise ValueError()
        if expected is None:return original
        token=result['accessToken'];client=result['client']
        if (not isinstance(token,str) or not 1<=len(token)<=8192 or any(not 33<=ord(c)<=126 for c in token)
                or not isinstance(client,dict) or set(client)!={'userAgent','version'}
                or any(not isinstance(v,str) or not 1<=len(v)<=2048 or any(not 32<=ord(c)<=126 for c in v) for v in client.values())):raise ValueError()
        return {'key':token,'extraHeaders':{'ChatGPT-Account-Id':original['accountId'],
            'originator':'r4os_studio','User-Agent':client['userAgent']},'clientVersion':client['version']}
    except ProjectFault:raise
    except (OSError,ValueError,TypeError,KeyError):
        raise ProjectFault('The original native OpenAI access service is unavailable. No model request was started.',503) from None


def prepare(providers,ident,label,account):
    """Called explicitly by the account owner while its identity lock is held."""
    api=ApiProviders(providers);ident=identity(ident);secret=reference(account)
    with api.connect(write=True) as db:
        row=db.execute('SELECT data,retired FROM providers WHERE id=?',(ident,)).fetchone()
        if row:
            value=api.current(db,ident)
            if value['kind']!=KIND:raise ProjectFault('This connection belongs to another provider.',409)
            stored=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',(ident,value['credentialRevision'])).fetchone()
            if value['enabled'] and stored and stored[0]==secret:return value
            if (db.execute("SELECT 1 FROM leases WHERE provider_id=? AND state!='released'",(ident,)).fetchone()
                    or db.execute("SELECT 1 FROM requests WHERE provider_id=? AND phase!='complete'",(ident,)).fetchone()):
                raise ProjectFault('Resolve the original native account workers before reconnecting.',409)
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='catalog_requests'").fetchone() and db.execute('SELECT 1 FROM catalog_requests WHERE provider_id=? AND held=1',(ident,)).fetchone():
                raise ProjectFault('The original native metadata operation is unconfirmed.',409)
            value.update(name=name(label),revision=value['revision']+1,credentialRevision=value['credentialRevision']+1,enabled=True,keyConfigured=True,updatedAt=now())
        else:
            stamp=now();value={'id':ident,'type':'api','kind':KIND,'name':name(label),'baseUrl':BASE,'protocol':'responses','auth':'bearer',
                'server':'custom','revision':1,'credentialRevision':1,'keyConfigured':True,'enabled':True,'status':'configured',
                'createdAt':stamp,'updatedAt':stamp,'runtime':'not-qualified'}
        db.execute('INSERT INTO secrets.credentials VALUES (?,?,?)',(ident,value['credentialRevision'],secret))
        api.cleanup(db,value);api.save(db,value)
        return value


async def retire(host,ident,remove=False):
    """Use existing admission, catalog, worker and credential end receipts."""
    import asyncio
    import uuid
    from api_catalog_host import recover
    api=ApiProviders(host.config['providers'])
    try:value=api.get(ident)
    except ProjectFault as error:
        if error.code in (404,410):return
        raise
    if value['kind']!=KIND:raise ProjectFault('This is not a native Studio connection.',409)
    operation='delete' if remove else 'disconnect'
    if not remove and not value['enabled'] and not value['keyConfigured']:return
    with api.connect() as db:
        pending=db.execute("SELECT * FROM requests WHERE provider_id=? AND phase!='complete'",(ident,)).fetchone()
        if pending:
            if pending['operation']!=operation:raise ProjectFault('Finish the original account disconnect before removing it.',409)
            data={'requestId':pending['id'],'revision':value['revision']-1}
        else:data={'requestId':str(uuid.uuid5(uuid.NAMESPACE_URL,ident+':'+operation+':'+str(value['revision']))),'revision':value['revision']}
    result=await asyncio.to_thread(api.mutate,operation,ident,data,False,False,True)
    if result['state']=='pending':
        await recover(host,ident)
        await host.handle({'operation':'cancel_provider','providerId':ident})
        await asyncio.to_thread(api.mutate,operation,ident,data,True,False,True)


def limits(providers,ident,expected):
    """Only existing account/rateLimits/read; no model, credits or reset consume."""
    import os
    api=ApiProviders(providers);private(api.parent,directory=True);path=api.parent/'.a.sock';expected=binding(expected)
    info=path.lstat()
    if not stat.S_ISSOCK(info.st_mode):
        raise ProjectFault('The original OpenAI account-limit service is unavailable.',503)
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(55);client.connect(str(path));client.sendall((encode({'action':'limits','id':identity(ident),'binding':expected})+'\n').encode());raw=b''
        while b'\n' not in raw:
            chunk=client.recv(16384)
            if not chunk or len(raw)+len(chunk)>524288:raise ProjectFault('The original OpenAI limits could not be confirmed.',503)
            raw+=chunk
    value=json.loads(raw)
    if 'error' in value:raise ProjectFault(value['error'],value.get('code',503))
    result=value['result']
    if binding(result['binding'])!=expected or not isinstance(result.get('usage'),dict):raise ProjectFault('The original OpenAI usage account changed.',409)
    return result
