"""The original whole-run end barrier shared by automatic session continuations."""
import json
from owner import binding
from model_operations import alive
from store import ProjectFault


async def require(host,store,sid):
    if store.db.execute('SELECT 1 FROM runs WHERE busy=1 LIMIT 1').fetchone() or any(binding(v)==(store.owner_type,store.owner_id) for v in host.active.values()):
        raise ProjectFault('The original workspace run has not fully ended.',423)
    source=store.db.execute('SELECT * FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1',(sid,)).fetchone()
    if source is None:return None
    if source['state']=='unknown':raise ProjectFault('The original run outcome is unknown. No automatic continuation was admitted.',409)
    if await host.active_unit(source['id']):raise ProjectFault('The original run service is still ending.',423)
    worker=json.loads(source['worker'] or '{}');config=json.loads(source['config'])
    if worker.get('pid') and alive(worker['pid'],worker.get('birth')):raise ProjectFault('The original worker process has not ended.',423)
    if (worker and config['engine'].get('kind')=='studio' or worker.get('runEndProtocol')==1) and worker.get('processEnd',{}).get('confirmed') is not True:
        raise ProjectFault('The original model/worker process group end is unconfirmed.',409)
    if store.db.execute("SELECT 1 FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND (t.state NOT IN ('completed','failed') OR t.result IS NULL) LIMIT 1",(sid,)).fetchone():
        raise ProjectFault('An original tool receipt has no confirmed end. No automatic continuation was admitted.',409)
    if config['engine'].get('kind')=='claude-code':
        from claude_history import ClaudeHistory
        if ClaudeHistory(store,sid).get()['phase'] not in ('allocated','ready'):raise ProjectFault('The original Claude history is unconfirmed.',409)
    return source
