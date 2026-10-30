"""Read-only budget for a confirmed current deployment; never guesses a path."""
import json
from contracts import DevelopmentFault
from deskrun import DEFAULT_WAIT_MS, launch_budget


def selected(store, deployment, vm):
    unavailable = {'available': False, 'reason': 'A verified Desktop deployment matching the current project and VM boot is required for its argument budget.'}
    try:
        parent = store.get(deployment['jobId']); target = deployment['target']
        if (not vm or deployment.get('role') != 'desktop' or parent['state'] != 'completed'
            or parent.get('projectRevision') != store.project['revision'] or deployment.get('pins') != store.project['pins']
            or deployment['projectId'] != store.id or target['vmId'] != store.project['vmId']
            or any(target[key] != vm[field] for key,field in (('vmId','id'),('vmRevision','revision'),('imageId','imageId'),('imageSha256','imageSha256')))):
            return unavailable
        path = store.projects / '.studio/development/Boots' / (target['vmId'] + '.json')
        if path.resolve(strict=True) != path or path.stat().st_size > 8192:return unavailable
        boot = json.loads(path.read_text())
        from lease import birth
        if (boot.get('connected') is not True or boot.get('bootId') != target['bootId']
            or boot.get('schema') != 1 or any(boot.get(k) != vm[f] for k,f in (('vmId','id'),('vmRevision','revision'),('imageId','imageId'),('imageSha256','imageSha256')))
            or birth(boot['pid']) != boot.get('birth')):return unavailable
        settings = store.settings()
        current = launch_budget(deployment,settings['arguments'],min(DEFAULT_WAIT_MS,settings['timeoutSeconds']*1000))
        return {'available':True,'binding':{'projectRevision':store.project['revision'],'settingsRevision':settings['revision'],
            'deploymentId':deployment['id'],'vmId':target['vmId'],'vmRevision':target['vmRevision'],'bootId':target['bootId']},
            'limitBytes':current['limitBytes'],'wrapperBytes':current['wrapperBytes'],
            'defaultWaitFixedBytes':launch_budget(deployment,'',DEFAULT_WAIT_MS)['fixedBytes'],
            'shortWaitFixedBytes':{str(i):launch_budget(deployment,'',i*1000)['fixedBytes'] for i in range(1,5)},'saved':current}
    except (DevelopmentFault,OSError,ValueError,KeyError,TypeError):return unavailable


def options(store,vm):
    if store.project['template'] != 'desktop':return None
    rows = store.db.execute('SELECT payload FROM deployments ORDER BY rowid DESC LIMIT 1').fetchall()
    if not rows:return {'available':False,'reason':'Deploy a verified Desktop application before calculating its bound argument budget.'}
    try:return selected(store,json.loads(rows[0][0]),vm)
    except (ValueError,TypeError):return {'available':False,'reason':'The saved Desktop deployment budget is unavailable.'}


def for_deployment(store,deployment):
    try:
        from contracts import identity
        path=store.r4os/'Instances'/identity(store.project['vmId'])/'vm.json'
        if path.resolve(strict=True)!=path or path.stat().st_size>65536:raise ValueError()
        return selected(store,deployment,json.loads(path.read_text()))
    except (DevelopmentFault,OSError,ValueError,KeyError,TypeError):
        return {'available':False,'reason':'The current Desktop deployment/VM argument binding is unavailable.'}
