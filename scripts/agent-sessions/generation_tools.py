"""Additive image-tool contract; no image is accepted without its output adapter."""
from store import ProjectFault

async def execute(worker,name,args,call_id):
    if name=='list_generated_images':return {'images':[],'available':False,'reason':'This worker release has no installed image output adapter yet.'}
    raise ProjectFault('Image import is unavailable until the generated-image preparation adapter is installed. No file was changed.',503)
