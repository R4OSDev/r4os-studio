"""Additive image-tool contract; no image is accepted without its output adapter."""
from store import ProjectFault

async def execute(worker,name,args,call_id):
    if name=='list_generated_images':
        from generated_images import GeneratedImages
        from session_store import encode
        return {'success':True,'output':encode({'images':GeneratedImages(worker.store,worker.session_id).list(),'generationEnabled':worker.config.get('nativeImageGeneration') is True})}
    raise ProjectFault('Image import is unavailable until the generated-image preparation adapter is installed. No file was changed.',503)
