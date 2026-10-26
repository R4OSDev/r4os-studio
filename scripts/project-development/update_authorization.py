"""Session provenance for v5 update contracts, independent of active skills."""
from contracts import DevelopmentFault

PERMISSIONS={'update_options':'read_update_package','read_update_plan':'read_update_package',
    'update_batch_preview':'read_update_package','package_artifact':'read_update_package',
    'update_job_list':'read_update_package','update_list':'read_update_package','read_update':'read_update_package','update_plan':'plan_update_package',
    'package':'build_update_package','update_probe':'check_update_vm','update_transfer':'upload_update_package',
    'update_install':'install_update_package','update_commit':'commit_update','update_verify':'verify_update',
    'update_recovery':'resume_update','wait_update':'read_update_package'}
RECOVERY_PERMISSIONS={'resume':'resume_update','resume-batch':'resume_update','abort-batch':'abort_update',
    'rollback-last':'rollback_update','cleanup':'cleanup_update_transport'}

def permission(operation,job=None,action=None):
    if operation=='wait_update' and job:operation=job['kind']
    if operation=='update_recovery':
        return RECOVERY_PERMISSIONS.get(action or (job or {}).get('recoveryAction'),'resume_update')
    return PERMISSIONS[operation]

def same_session(value,owner):
    if not owner or owner.get('sessionId') is None:return
    if value.get('sessionId')!=owner['sessionId']:
        raise DevelopmentFault('This update input belongs to another session or to the browser operator. Build/package within this session.',403)

def parent(store,kind,ident,owner):
    if not owner or owner.get('sessionId') is None:return
    if kind=='artifact':
        value=store.artifact_metadata(ident);same_session(store.get(value['buildId']),owner)
    elif kind=='plan':
        from update_plans import read
        value=read(store,ident);same_session(value.get('owner') or {},owner)
    elif kind=='package':
        from package_jobs import artifact
        value=artifact(store,ident);same_session(store.get(value['jobId']),owner)
    elif kind=='transfer':same_session(store.get(ident),owner)
    elif kind=='update':
        from update_state import read
        same_session(read(store,ident),owner)
    else:raise DevelopmentFault('Unknown update input provenance.',400)

def filtered_options(store,value,owner):
    if not owner or owner.get('sessionId') is None:return value
    result={**value,'artifacts':[],'plans':[]}
    for item in value['artifacts']:
        if store.get(item['buildId']).get('sessionId')==owner['sessionId']:result['artifacts'].append(item)
    result['plans']=[plan for plan in value['plans'] if (plan.get('owner') or {}).get('sessionId')==owner['sessionId']]
    return result
