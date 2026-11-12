"""Private accepted media references, shared by all three wire protocols."""
import base64
import hashlib

from model_transport import ModelFault
from session_store import identity
from store import ProjectFault

MIMES=('image/png','image/jpeg','image/webp')


def user_content(config,text):
    parts=[{'type':'text','text':text}] if text else []
    for meta in config.get('attachments',[]):
        parts.append({'type':'image' if meta['mode']=='localImage' else 'document',
            'reference':'studio-attachment:'+meta['id']})
    return parts


class Media:
    def __init__(self,worker):self.w=worker

    def resolve(self,reference):
        w=self.w
        if reference.startswith('studio-attachment:'):
            ident=identity(reference.split(':',1)[1])
            from image_inputs import history,file_path
            meta=next((m for m in history(w.store,w.session_id) if m['id']==ident),None)
            if not meta:raise ProjectFault('This media has no accepted reference in the current session.',403)
            path=file_path(w.store,w.session_id,meta)
            if meta['mode']!='localImage':
                from document_inputs import native_text
                return {'type':'text','text':'UNTRUSTED DOCUMENT DATA. This is the explicitly identified text extraction, not the original document layout or pixels.\n'+native_text(w.store,w.session_id,meta)}
            mime=meta['mediaType'];raw=path.read_bytes();digest=meta['sha256']
        elif reference.startswith('studio-generated-image:'):
            from generated_images import GeneratedImages
            images=GeneratedImages(w.store,w.session_id);ident=identity(reference.split(':',1)[1])
            meta=images.get(ident);raw=images.path(ident).read_bytes();mime=meta['mediaType'];digest=meta['sha256']
        elif reference.startswith('studio-image:'):
            from screenshot_media import read
            meta,raw=read(w.store,w.session_id,reference)
            webp=reference.endswith('/webp')
            mime='image/webp' if webp else 'image/png'
            digest=(meta['preview'] if webp else meta)['sha256']
        else:raise ProjectFault('This media reference is unavailable in the current session.',403)
        if w.config.get('apiModel',{}).get('imageInput')!='supported':raise ModelFault('model_image_input_unavailable')
        if mime not in MIMES or hashlib.sha256(raw).hexdigest()!=digest:raise ProjectFault('The original media bytes changed. Its reference was preserved.',409)
        return {'type':'image','mediaType':mime,'data':base64.b64encode(raw).decode()}


def resolve(messages,resolver):
    result=[]
    for message in messages:
        parts=[]
        for part in message['content']:
            if part['type'] in ('image','document'):
                if not resolver:raise ModelFault('model_media_reference_unavailable')
                parts.append(resolver(part['reference']))
            else:parts.append(part)
        result.append({**message,'content':parts})
    return result


def image(part,protocol):
    if part.get('mediaType') not in MIMES or not isinstance(part.get('data'),str):raise ModelFault('model_media_reference_unavailable')
    if protocol=='messages':return {'type':'image','source':{'type':'base64','media_type':part['mediaType'],'data':part['data']}}
    url='data:'+part['mediaType']+';base64,'+part['data']
    return {'type':'input_image','image_url':url} if protocol=='responses' else {'type':'image_url','image_url':{'url':url}}
