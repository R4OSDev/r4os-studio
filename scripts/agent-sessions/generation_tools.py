"""Frozen image tools: private metadata or an authorized binary import."""
from store import ProjectFault

async def execute(worker,name,args,call_id):
    if name=='list_generated_images':
        from generated_images import GeneratedImages
        from session_store import encode
        return {'success':True,'output':encode({'images':GeneratedImages(worker.store,worker.session_id).list(),'generationEnabled':worker.config.get('nativeImageGeneration') is True})}
    from image_import import import_image
    try:return await import_image(worker,args,call_id)
    except ProjectFault as error:
        import hashlib
        from generated_images import GeneratedImages
        token=hashlib.sha256((worker.run_id+':'+call_id).encode()).hexdigest()
        pending=(GeneratedImages(worker.store,worker.session_id).root()/'Imports'/(token+'.json')).exists()
        return {'success':False,'error':'unknown' if pending else 'conflict','output':str(error),**({'partialChangesPossible':True} if pending else {})}
