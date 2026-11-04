"""Conservative private cache collection after a confirmed source worker end."""
import json
import re
import shutil


def prune(api,db,root,ident):
    with api.locked(root,ident):return collect(api,db,root,ident)


def collect(api,db,root,ident):
    sources=set();runtimes=set();live=[]
    for row in db.execute('SELECT hash FROM revisions WHERE skill_id=?',(ident,)):
        raw,_=api.regular(root/ident/'Revisions'/row[0]/'revision.json')
        binding=json.loads(raw).get('sourceBinding')
        if binding:
            api.source_binding.validate(binding,api.SkillFault)
            sources.add(binding['commit'])
            if binding['runtime']:runtimes.add(binding['runtime']['path'])
    jobs=[json.loads(r[0]) for r in db.execute('SELECT metadata FROM skill_source_jobs WHERE skill_id=?',(ident,))]
    for job in jobs:
        result=job.get('result') or {}
        if job.get('commit'):sources.add(job['commit'])
        if result.get('runtime'):runtimes.add(result['runtime']['path'])
        if not job.get('processEndConfirmed') or job['phase']=='unknown':live.append(job)
    # A pending original may not have published its final build key yet. Its
    # whole skill cache is retained rather than guessing from a progress phase.
    if live:return dict(pruned=[],pendingOriginals=len(live))
    removed=[]
    parent=root/ident
    for commit in (parent/'Runtimes').iterdir() if (parent/'Runtimes').exists() else []:
        if not re.fullmatch('[a-f0-9]{40}',commit.name):continue
        api.folder(commit)
        for cache in commit.iterdir():
            if not re.fullmatch('[a-f0-9]{64}',cache.name):continue
            relative=cache.relative_to(parent).as_posix()
            if relative in runtimes:continue
            api.folder(cache)
            if not (cache/'runtime.json').is_file():continue
            shutil.rmtree(cache);api.sync(commit);removed.append(relative)
    # Only stages with this exact terminal request identity are collected.
    for job in jobs:
        if job['phase'] not in ('failed','cancelled','complete'):continue
        rid=api.identity(job['requestId'])
        candidates=[parent/'Sources'/('.stage-'+rid)]
        if job.get('commit'):candidates.append(parent/'Runtimes'/job['commit']/('.stage-'+rid))
        for stage in candidates:
            if not stage.exists() and not stage.is_symlink():continue
            api.folder(stage);shutil.rmtree(stage);api.sync(stage.parent);removed.append(stage.relative_to(parent).as_posix())
    return dict(pruned=removed,pendingOriginals=0)
