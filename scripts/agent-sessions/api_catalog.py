"""Revisioned API model catalogs and original metadata-only request journals."""
import hashlib
import json
import os
from pathlib import Path
import signal

from api_provider_store import ApiProviders,key
from api_model_info import normalized,present,native
from session_store import identity,encode,now
from store import ProjectFault

MAX_METADATA=256
MAX_MODELS=320


def has(db,table):return db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE name=? AND type='table'",(table,)).fetchone() is not None


class Catalogs:
    def __init__(self,providers):self.api=ApiProviders(providers)

    def schema(self,db):
        db.execute('CREATE TABLE IF NOT EXISTS model_catalogs(provider_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS catalog_requests(
            id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,operation TEXT NOT NULL,fingerprint TEXT NOT NULL,
            binding TEXT NOT NULL,phase TEXT NOT NULL,held INTEGER NOT NULL,child TEXT,result TEXT,created_at TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS catalog_request_provider ON catalog_requests(provider_id,held)')

    def raw(self,db,provider):
        row=db.execute('SELECT * FROM model_catalogs WHERE provider_id=?',(provider['id'],)).fetchone() if has(db,'model_catalogs') else None
        return (row['revision'],json.loads(row['data'])) if row else (0,{'configRevision':provider['revision'],'models':[],
            'checkedAt':None,'checkedConfigRevision':None,'checkedCredentialRevision':None,'truncated':False})

    def listing(self,ident):
        with self.api.connect() as db:
            provider=self.api.current(db,ident);revision,data=self.raw(db,provider)
            return {'providerId':ident,'revision':revision,'configRevision':data['configRevision'],
                'stale':data['configRevision']!=provider['revision'],'checkedAt':data['checkedAt'],
                'metadataCurrent':data.get('checkedConfigRevision')==provider['revision'] and data['checkedCredentialRevision']==provider['credentialRevision'],
                'checkedCredentialRevision':data['checkedCredentialRevision'],'truncated':data['truncated'],
                'models':[present(value,provider['protocol']) for value in data['models']]}

    def native_models(self,ident):
        with self.api.connect() as db:
            provider=self.api.current(db,ident)
            if not has(db,'model_catalogs') or not db.execute('SELECT 1 FROM model_catalogs WHERE provider_id=?',(ident,)).fetchone():return None
            _,data=self.raw(db,provider)
            if data['configRevision']!=provider['revision']:return []
            return [model for value in data['models'] if (model:=native(value,provider['protocol'])) is not None]

    def request(self,db,ident,rid):
        row=db.execute('SELECT * FROM catalog_requests WHERE id=? AND provider_id=?',(identity(rid),identity(ident))).fetchone() if has(db,'catalog_requests') else None
        if row is None:raise ProjectFault('Original model request not found.',404)
        return row

    def receipt(self,ident,rid):
        with self.api.connect() as db:
            row=self.request(db,ident,rid)
            return json.loads(row['result']) if row['result'] else {'requestId':rid,'providerId':ident,'state':'pending'}

    def original(self,db,ident,data,operation):
        if not isinstance(data,dict):raise ProjectFault('Invalid model request.',400)
        rid=identity(data.get('requestId'));ident=identity(ident)
        fingerprint=hashlib.sha256(encode({'providerId':ident,'operation':operation,'input':data}).encode()).hexdigest()
        old=db.execute('SELECT * FROM catalog_requests WHERE id=?',(rid,)).fetchone()
        if old:
            if old['provider_id']!=ident or old['fingerprint']!=fingerprint:raise ProjectFault('This original request belongs to different model input.',409)
            return rid,fingerprint,json.loads(old['result']) if old['result'] else {'requestId':rid,'providerId':ident,'state':'pending'}
        return rid,fingerprint,None

    def save_model(self,ident,data):
        self.api.get(ident)
        with self.api.connect(write=True) as db:
            self.schema(db);rid,fingerprint,old=self.original(db,ident,data,'save_model')
            if old:return old
            if set(data)!={'requestId','providerRevision','catalogRevision','model'}:raise ProjectFault('Invalid model settings fields.',400)
            provider=self.api.current(db,ident);revision,catalog=self.raw(db,provider)
            if (type(data['providerRevision']) is not int or data['providerRevision']!=provider['revision']
                    or type(data['catalogRevision']) is not int or data['catalogRevision']!=revision):
                raise ProjectFault('Provider or model settings changed. Reload before saving.',409)
            value=normalized(data['model']);value['source']={'kind':'manual','recordedAt':now()}
            if catalog['configRevision']!=provider['revision']:catalog['models']=[]
            previous=next((v for v in catalog['models'] if v['id']==value['id']),None)
            if previous:catalog['models'][catalog['models'].index(previous)]=value
            else:
                if len(catalog['models'])>=MAX_MODELS:raise ProjectFault('The bounded model catalog is full.',409)
                catalog['models'].append(value)
            catalog['configRevision']=provider['revision']
            # Saving explicit facts is not a newly authenticated metadata check.
            result={'requestId':rid,'providerId':ident,'state':'complete','catalogRevision':revision+1,'modelId':value['id']}
            db.execute('INSERT INTO model_catalogs VALUES (?,?,?) ON CONFLICT(provider_id) DO UPDATE SET revision=excluded.revision,data=excluded.data',
                (ident,revision+1,encode(catalog)))
            db.execute("INSERT INTO catalog_requests VALUES (?,?,?,?,?,'complete',0,NULL,?,?)",(rid,ident,'save_model',fingerprint,'{}',encode(result),now()))
            return result

    def start_refresh(self,ident,data,allowed=True):
        self.api.get(ident)
        with self.api.connect(write=True) as db:
            self.schema(db);rid,fingerprint,old=self.original(db,ident,data,'refresh')
            if old:return old,False
            if not allowed:raise ProjectFault('Metadata checks are busy. No new check was admitted.',429)
            if set(data)!={'requestId','providerRevision'}:raise ProjectFault('Invalid metadata check fields.',400)
            provider=self.api.current(db,ident)
            if type(data['providerRevision']) is not int or data['providerRevision']!=provider['revision']:
                raise ProjectFault('Provider settings changed. Reload before checking metadata.',409)
            if not provider['enabled']:raise ProjectFault('Enable this API connection and configure its key before checking metadata.',409)
            if db.execute("SELECT 1 FROM catalog_requests WHERE provider_id=? AND phase!='complete'",(ident,)).fetchone():
                raise ProjectFault('Read or reconcile the original metadata request before another check.',409)
            binding={k:provider[k] for k in ('id','kind','baseUrl','protocol','auth','revision','credentialRevision')}
            db.execute("INSERT INTO catalog_requests VALUES (?,?,?,?,?,'reserved',0,NULL,NULL,?)",(rid,ident,'refresh',fingerprint,encode(binding),now()))
            return {'requestId':rid,'providerId':ident,'state':'pending'},True

    def binding(self,ident,rid):
        with self.api.connect() as db:return json.loads(self.request(db,ident,rid)['binding'])

    def claim(self,ident,rid,child):
        from attachment_store import birth
        if (set(child)!={'pid','birth','script'} or type(child['pid']) is not int or child['pid']<=0
                or birth(child['pid'])!=child['birth'] or (Path('/proc')/str(child['pid'])).stat().st_uid!=os.geteuid()
                or child['script']!=str(Path(__file__).with_name('api-models.mjs').resolve(strict=True))):
            raise ProjectFault('The original metadata helper identity is unavailable.',503)
        with self.api.connect(write=True) as db:
            row=self.request(db,ident,rid);binding=json.loads(row['binding']);provider=self.api.current(db,ident)
            if row['phase']!='reserved' or not provider['enabled'] or any(provider[k]!=v for k,v in binding.items()):
                raise ProjectFault('The original metadata admission changed. No replacement request was sent.',409)
            credential=None
            if binding['auth']=='bearer':
                secret=db.execute('SELECT value FROM secrets.credentials WHERE provider_id=? AND revision=?',(ident,binding['credentialRevision'])).fetchone()
                if secret is None:raise ProjectFault('The selected metadata credential revision is unavailable.',409)
                credential=key(secret[0])
            db.execute("UPDATE catalog_requests SET held=1,phase='active',child=? WHERE id=?",(encode(child),rid))
            return credential

    def finish(self,ident,rid,models=None,error=None,child=None,truncated=False):
        with self.api.connect(write=True) as db:
            row=self.request(db,ident,rid)
            if row['phase']=='complete':return json.loads(row['result'])
            if row['held']:
                if not child or json.loads(row['child'] or 'null')!=child or self.alive(child):
                    raise ProjectFault('The original metadata transport is unconfirmed. Its credential was preserved.',503)
            provider=self.api.current(db,ident,retired=True);binding=json.loads(row['binding'])
            if not error and (not provider['enabled'] or any(provider[k]!=v for k,v in binding.items())):
                error='Provider settings changed before metadata publication. Check the current connection explicitly.'
            result={'requestId':rid,'providerId':ident,'state':'failed' if error else 'complete'}
            if error:result['error']=error
            else:
                if not isinstance(models,list) or len(models)>MAX_METADATA:raise ProjectFault('The model metadata response exceeds its bound.',503)
                revision,catalog=self.raw(db,provider);seen=set();values=[]
                for entry in models:
                    value=normalized(entry)
                    if value['id'] in seen:raise ProjectFault('The model metadata contains duplicate IDs.',503)
                    seen.add(value['id']);value['source']={'kind':'metadata','recordedAt':now(),'url':binding['baseUrl']+'/models'};values.append(value)
                # Explicit model contracts survive a metadata refresh, including
                # exact manual IDs not advertised by this metadata endpoint.
                manual=[v for v in catalog['models'] if catalog['configRevision']==provider['revision'] and v.get('source',{}).get('kind')=='manual']
                manual_ids={v['id'] for v in manual};values=[v for v in values if v['id'] not in manual_ids]
                if len(values)+len(manual)>MAX_MODELS:values=values[:MAX_MODELS-len(manual)];truncated=True
                values+=manual
                catalog={'configRevision':provider['revision'],'models':values,'checkedAt':now(),
                    'checkedConfigRevision':provider['revision'],
                    'checkedCredentialRevision':binding['credentialRevision'],'truncated':bool(truncated)}
                db.execute('INSERT INTO model_catalogs VALUES (?,?,?) ON CONFLICT(provider_id) DO UPDATE SET revision=excluded.revision,data=excluded.data',
                    (ident,revision+1,encode(catalog)))
                result['catalogRevision']=revision+1
            db.execute("UPDATE catalog_requests SET phase='complete',held=0,result=? WHERE id=?",(encode(result),rid))
            self.api.cleanup(db,provider)
            return result

    def unknown(self,ident,rid):
        with self.api.connect(write=True) as db:
            row=self.request(db,ident,rid)
            if row['phase']=='complete':return
            result={'requestId':rid,'providerId':ident,'state':'unknown',
                'error':'Original metadata transport closure is unconfirmed. Its credentials and request were preserved.'}
            db.execute("UPDATE catalog_requests SET phase='unknown',result=? WHERE id=?",(encode(result),rid))

    def alive(self,child):
        from attachment_store import birth
        try:
            if (Path('/proc')/str(child['pid'])).stat().st_uid!=os.geteuid():return False
            return birth(child['pid'])==child['birth']
        except (OSError,ValueError,KeyError):return False

    def pending(self,ident=None):
        with self.api.connect() as db:
            if not has(db,'catalog_requests'):return []
            query="SELECT * FROM catalog_requests WHERE phase!='complete'";args=()
            if ident:query+=' AND provider_id=?';args=(identity(ident),)
            return [dict(row) for row in db.execute(query,args)]

    def signal_original(self,child):
        if not self.alive(child):return
        try:descriptor=os.pidfd_open(child['pid'])
        except ProcessLookupError:return
        try:
            if not self.alive(child):return
            args=(Path('/proc')/str(child['pid'])/'cmdline').read_bytes().split(b'\0')
            script=Path(child['script'])
            if (script.name!='api-models.mjs' or script.resolve(strict=True)!=script
                    or script.stat().st_uid!=0 or script.stat().st_mode&0o022
                    or args[:2]!=[b'/usr/bin/node',str(script).encode()]):
                raise ProjectFault('The original metadata process binding is unconfirmed.',503)
            try:signal.pidfd_send_signal(descriptor,signal.SIGTERM)
            except ProcessLookupError:pass
        finally:os.close(descriptor)
