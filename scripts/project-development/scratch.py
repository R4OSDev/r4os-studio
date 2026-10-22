"""Only verified successful build scratch is disposable; durable evidence stays."""
import shutil
from contracts import DevelopmentFault, identity


def retire(store, job):
    if job['kind'] != 'build' or job['state'] != 'completed' or not job.get('artifactId'): return False
    store.artifact(job['artifactId'])
    path = store.root / 'Work' / identity(job['id'])
    if not path.exists(): return False
    if path.resolve(strict=True) != path: raise DevelopmentFault('Invalid private build scratch. It was preserved.')
    shutil.rmtree(path); return True
