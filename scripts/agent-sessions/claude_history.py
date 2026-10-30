"""Immutable native-session identity and byte-preserving resume admission."""
import hashlib
from contextlib import nullcontext
import json
import os
from pathlib import Path

from api_provider_store import private
from claude_runtime import binding as runtime_binding
from session_store import identity,encode,now
from store import ProjectFault


def inventory(root):
    """Integrity metadata only; never reconstruct or rewrite a native transcript."""
    private(root,directory=True);result={};size=0
    for base,dirs,files in os.walk(root,followlinks=False):
        if len(Path(base).relative_to(root).parts)>16:raise ProjectFault('The original native history exceeds its directory bound.',409)
        for name in dirs:private(Path(base)/name,directory=True)
        for name in files:
            path=Path(base)/name;private(path);size+=path.stat().st_size
            if len(result)>=4096 or size>2*1024**3:raise ProjectFault('The original native history exceeds its storage bound. Existing bytes were preserved.',409)
            if path.suffix=='.jsonl':
                with path.open('rb') as stream:
                    while line:=stream.readline(64*1024**2+1):
                        if len(line)>64*1024**2 or not line.endswith(b'\n'):
                            raise ProjectFault('The original native history has an incomplete record. Existing bytes were preserved.',409)
                        try:
                            if not isinstance(json.loads(line),dict):raise ValueError()
                        except (ValueError,UnicodeError):raise ProjectFault('The original native history is unreadable. No replacement conversation was created.',409) from None
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            result[path.relative_to(root).as_posix()]={'bytes':path.stat().st_size,'sha256':digest}
    return result


class ClaudeHistory:
    def __init__(self,store,sid):self.store=store;self.sid=identity(sid)

    def table(self,write=False):
        db=self.store.db
        if write:db.execute('CREATE TABLE IF NOT EXISTS claude_sessions(session_id TEXT PRIMARY KEY REFERENCES sessions(id),data TEXT NOT NULL)')
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='claude_sessions'").fetchone() is not None

    def get(self):
        self.store.row(self.sid)
        row=self.store.db.execute('SELECT data FROM claude_sessions WHERE session_id=?',(self.sid,)).fetchone() if self.table() else None
        if not row:raise ProjectFault('The original native Claude session binding is unavailable. No replacement was created.',409)
        value=json.loads(row[0]);session=self.store.get(self.sid)
        if (value.get('schema')!=1 or value.get('owner')!={'type':self.store.owner_type,'id':self.store.owner_id}
            or value.get('sessionId')!=self.sid or value.get('providerId')!=session['providerId']
            or session['engine'].get('kind')!='claude-code' or value.get('toolProfile')!=session['engine']['profile']
            or session['engine'].get('claude')!=value.get('runtime')):
            raise ProjectFault('The native Claude owner/provider/runtime binding changed. Original history was preserved.',409)
        return value

    def create(self,provider):
        session=self.store.get(self.sid)
        if session['engine'].get('kind')!='claude-code' or session['providerId']!=provider['id']:
            raise ProjectFault('A native Claude binding requires its own original Studio session.',409)
        if self.table() and self.store.db.execute('SELECT 1 FROM claude_sessions WHERE session_id=?',(self.sid,)).fetchone():return self.get()
        import uuid
        from claude_provider_store import account_identity
        native_id=str(uuid.uuid4());frozen=runtime_binding(provider,self.sid,native_id)
        value={'schema':1,'sessionId':self.sid,'owner':{'type':self.store.owner_type,'id':self.store.owner_id},
            'providerId':provider['id'],'accountIdentity':account_identity(provider.get('account')),
            'toolProfile':session['engine']['profile'],'runtime':frozen,'phase':'allocated',
            'activeRunId':None,'lastReceipt':None,'inventory':{},'updatedAt':now()}
        # SessionStore.create owns its original creation transaction. Never
        # commit that transaction before its request receipt is stored.
        with (nullcontext() if self.store.db.in_transaction else self.store.db):
            self.table(write=True)
            # Store identity and native binding together. A lost response reads
            # the same UUID; it never allocates another native conversation.
            engine={**session['engine'],'claude':frozen}
            self.store.db.execute('UPDATE sessions SET engine=? WHERE id=?',(encode(engine),self.sid))
            self.store.db.execute('INSERT INTO claude_sessions VALUES (?,?)',(self.sid,encode(value)))
        return value

    def paths(self):
        self.get();root=self.store.directory/self.sid
        private(root,directory=True,create=True)
        root=root/'Claude';private(root,directory=True,create=True)
        for name in ('Projects','Runtime'):private(root/name,directory=True,create=True)
        return {'root':root,'history':root/'Projects','runtime':root/'Runtime'}

    def save(self,value):
        value={**value,'updatedAt':now()}
        self.store.db.execute('UPDATE claude_sessions SET data=? WHERE session_id=?',(encode(value),self.sid));return value

    def prepare(self,run_id):
        from run_store import get_run
        run_id=identity(run_id);run=get_run(self.store,run_id);config=json.loads(run['config']);saved=self.get()
        if (run['session_id']!=self.sid or not run['busy'] or run['state']=='stopping' or config['providerId']!=saved['providerId']
            or config['engine'].get('claude')!=saved['runtime'] or config['engine'].get('kind')!='claude-code'):
            raise ProjectFault('This native Claude run does not match its original frozen session.',409)
        if saved['phase'] not in ('allocated','ready'):
            raise ProjectFault('The original native Claude execution is unconfirmed. It was not resumed or replayed.',409)
        paths=self.paths();current=inventory(paths['history'])
        if current!=saved['inventory'] or saved['phase']=='ready' and not current:
            raise ProjectFault('The original native Claude history is missing or changed. Existing bytes were preserved.',409)
        pending=self.store.db.execute("SELECT 1 FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND (t.result IS NULL OR t.state='unknown') LIMIT 1",(self.sid,)).fetchone()
        if pending:raise ProjectFault('An original native tool effect is unconfirmed. No Claude execution was started.',409)
        mode='new' if saved['phase']=='allocated' else 'resume'
        with self.store.db:self.save({**saved,'phase':'opening','activeRunId':run_id})
        return {'mode':mode,'runtime':saved['runtime'],'paths':paths,'historyConfirmed':mode=='resume'}

    def finish(self,run_id,receipt):
        from run_store import get_run
        run_id=identity(run_id);run=get_run(self.store,run_id);saved=self.get()
        if saved['activeRunId']!=run_id or saved['phase'] not in ('opening','active'):
            raise ProjectFault('The original native Claude completion binding is unavailable.',409)
        valid=(isinstance(receipt,dict) and set(receipt)=={'nativeSessionId','nativeResultId','studioRequestId','subtype','nativeClosed','historyReadable'}
            and receipt['nativeSessionId']==saved['runtime']['nativeSessionId'] and receipt['studioRequestId']==run['request_id']
            and receipt['nativeClosed'] is True and receipt['historyReadable'] is True
            and receipt['subtype'] in ('success','error_max_turns','error_during_execution','error_max_budget_usd','error_max_structured_output_retries'))
        if valid:
            try:identity(receipt['nativeResultId'])
            except ProjectFault:valid=False
        pending=self.store.db.execute("SELECT 1 FROM tools WHERE run_id=? AND (result IS NULL OR state='unknown') LIMIT 1",(run_id,)).fetchone()
        current=inventory(self.paths()['history'])
        valid=valid and not pending and bool(current)
        with self.store.db:return self.save({**saved,'phase':'ready' if valid else 'unknown','activeRunId':None,
            'lastReceipt':receipt if valid else None,'inventory':current})

    def unconfirmed(self,run_id):
        saved=self.get()
        if saved['activeRunId']==identity(run_id):
            with self.store.db:self.save({**saved,'phase':'unknown','activeRunId':None})

    def unstarted(self,run_id,prepared,receipt):
        """Revoke only a positively closed opening with zero submitted input.

        Unchanged original bytes and no tool intents are mandatory. This does
        not recover an interrupted model execution or create a new native ID.
        """
        run_id=identity(run_id);saved=self.get()
        from run_store import get_run
        request_id=get_run(self.store,run_id)['request_id']
        valid=(saved['activeRunId']==run_id and saved['phase']=='opening' and isinstance(prepared,dict)
            and prepared.get('mode') in ('new','resume') and isinstance(receipt,dict)
            and prepared.get('runtime')==saved['runtime']
            and (prepared['mode']=='new' and not saved['inventory'] and saved['lastReceipt'] is None
                or prepared['mode']=='resume' and prepared.get('historyConfirmed') is True and bool(saved['inventory']) and bool(saved['lastReceipt']))
            and receipt.get('nativeSessionId')==saved['runtime']['nativeSessionId']
            and receipt.get('studioRequestId')==request_id
            and receipt.get('promptSubmitted') is False and receipt.get('resultId') is None
            and receipt.get('originalStreamConfirmed') is True)
        if not valid:return False
        pending=self.store.db.execute('SELECT 1 FROM tools WHERE run_id=? LIMIT 1',(run_id,)).fetchone()
        try:unchanged=inventory(self.paths()['history'])==saved['inventory']
        except (OSError,ProjectFault):return False
        if pending or not unchanged:return False
        with self.store.db:self.save({**saved,'phase':'allocated' if prepared['mode']=='new' else 'ready','activeRunId':None})
        return True
