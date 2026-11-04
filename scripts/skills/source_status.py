"""Read the bound installation probe without starting any analysis process."""
import hashlib
import json


def read(api,db,root,ident):
    current=api.detail(db,root,ident)
    binding=api.source_binding.current(api,db,root,ident,current['skill']['activeHash'])
    if not binding or not binding.get('runtime'):return dict(ready=False,reason='No managed runtime is active.')
    try:
        import runtime_spec
        runtime,manifest,catalog=runtime_spec.load(root,ident,binding)
        record=next(file for file in manifest['files'] if file['path']=='Readiness.json')
        raw=runtime_spec.read(runtime/'Readiness.json',1024*1024)
        if len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError()
        probe=json.loads(raw)
        if probe['server']['exactCatalogue'] is not True or probe['server']['tools']!=len(catalog['tools']):raise ValueError()
        result=probe['session']['structuredContent']['result']
        programs=manifest['programs']
        return dict(ready=True,commit=binding['commit'],version=manifest['version'],tools=len(catalog['tools']),
            packageHash=current['skill']['activeHash'],manifestHash=binding['runtime']['manifestHash'],
            node=manifest['node']['version'],npm=manifest['node']['npmVersion'],
            programs=[dict(id=p['id'],version=p['version'],origin=p['origin']) for p in programs['artifacts']],
            debianArchives=len(programs['debianArchives']),externalRequirements=programs['externalRequirements'],
            availability=result['tool_availability'],scope=probe['scope'])
    except (OSError,ValueError,KeyError,TypeError,StopIteration):
        return dict(ready=False,reason='The bound installation proof is unavailable or changed. Preserve its original preparation request.')
