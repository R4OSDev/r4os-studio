"""Ordered native content, explicit attachment provenance and frozen instructions."""
import base64
import hashlib

from claude_runtime import input_profile
from session_store import encode
from store import ProjectFault


def sha(value):return hashlib.sha256(value).hexdigest()


def content_digest(parts):
    descriptors=[]
    for part in parts:
        if part['type']=='text':descriptors.append({'type':'text','sha256':sha(part['text'].encode())})
        elif part['type']=='image':
            source=part['source'];raw=base64.b64decode(source['data'],validate=True)
            descriptors.append({'type':'image','mediaType':source['media_type'],'size':len(raw),'sha256':sha(raw)})
        else:raise ProjectFault('This native Claude content block is unavailable.',409)
    return sha(encode(descriptors).encode())


def qualify_images(store,sid,session,providers,records):
    images=[m for m in records if m['mode']=='localImage']
    if not images:return None
    from session_store import provider_models
    model=next((m for m in provider_models(providers,session['providerId']) if m['id']==session['model']),None)
    if not model or model.get('imageInputs')!='supported':
        raise ProjectFault('This Claude model has no qualified image input. Read its native catalog or choose a qualified image model; the original uploads were preserved.',409)
    if not session['model'].startswith('claude-'):
        raise ProjectFault('The original Claude image model is outside its qualified input profile.',409)
    return ['text','image']


def content(store,sid,text,config):
    from image_inputs import file_path
    from document_inputs import native_text
    policy=input_profile();parts=[{'type':'text','text':text}] if text else [];image_bytes=0
    for meta in config.get('attachments',[]):
        if meta['mode']=='localImage':
            if (config.get('claudeModel',{}).get('imageInput')!='supported' or not config['model'].startswith('claude-')
                or meta['mediaType'] not in policy['imageMediaTypes'] or meta['size']>policy['maxImageBytes']):
                raise ProjectFault('This Claude image requires a qualified model and PNG/JPEG/WebP of at most4 MiB. The original upload was preserved.',409)
            raw=file_path(store,sid,meta).read_bytes()
            if len(raw)!=meta['size'] or sha(raw)!=meta['sha256']:raise ProjectFault('The original Claude image changed. No input was submitted.',409)
            image_bytes+=len(raw)
            manifest={key:meta[key] for key in ('id','name','size','mediaType','sha256','mode','width','height')}
            parts.append({'type':'text','text':encode({'kind':'studio_attachment_metadata',**manifest})})
            parts.append({'type':'image','source':{'type':'base64','media_type':meta['mediaType'],'data':base64.b64encode(raw).decode('ascii')}})
        else:parts.append({'type':'text','text':native_text(store,sid,meta)})
    if image_bytes>policy['maxImageBytesPerSend'] or len(encode(parts).encode())>policy['maxNativeInputBytes']:
        raise ProjectFault('The bounded Claude input exceeds8 MiB of image data or12 MiB of native content. All original uploads were preserved.',409)
    if not parts:raise ProjectFault('The original Claude input has no text or readable attachment.',409)
    return parts


def freeze(store,sid,data,config):
    from instructions import compose
    policy=input_profile();prompt=compose(config);raw=prompt.encode()
    # Reserve space for the fixed native tool/GOAL boundary added by namespace.
    if len(raw)>124928:raise ProjectFault('The frozen Claude instructions exceed their bounded native contract. Reduce the selected prompt/skills before sending.',409)
    config['claudeInstructions']={'profileId':policy['id'],'sha256':sha(raw),'bytes':len(raw)}
    if not config.get('attachments'):return
    parts=content(store,sid,data['text'],config)
    config['claudeInput'].update(profileId=policy['id'],contentSha256=content_digest(parts))


def prepared_input(store,sid,run_id,config):
    frozen=config.get('claudeInput',{})
    if 'contentSha256' not in frozen:return None
    from run_store import request_text
    if frozen.get('profileId')!=input_profile()['id']:raise ProjectFault('The frozen Claude input profile changed.',409)
    text=request_text(store,run_id);parts=content(store,sid,text,config)
    if sha(text.encode())!=frozen['textSha256'] or content_digest(parts)!=frozen['contentSha256']:
        raise ProjectFault('The accepted native Claude content changed. Its original request was preserved.',409)
    return {'profileId':frozen['profileId'],'requestId':frozen['requestId'],'textSha256':frozen['textSha256'],
        'contentSha256':frozen['contentSha256'],'content':parts}
