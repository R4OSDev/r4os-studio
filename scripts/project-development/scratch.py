"""Only verified successful build scratch is disposable; durable evidence stays."""
import shutil
from contracts import DevelopmentFault, identity


def retire(store, job, verified_artifact=None):
    if job['kind'] != 'build' or job['state'] != 'completed' or not job.get('artifactId'): return False
    path = store.root / 'Work' / identity(job['id'])
    if not path.exists(): return False
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid private build scratch. It was preserved.')
    # A caller may reuse the receipt it verified synchronously in this operation.
    artifact = verified_artifact if verified_artifact is not None else store.artifact(job['artifactId'])
    if (artifact['id'] != job['artifactId'] or artifact['buildId'] != job['id'] or artifact['projectId'] != store.id):
        raise DevelopmentFault('The verified artifact belongs to another build. Scratch was preserved.')
    shutil.rmtree(path); return True
