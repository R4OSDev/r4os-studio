"""Bind SDK-parsed resource declarations to the immutable captured source, without rewriting R4MF."""
from contracts import DevelopmentFault,relative


def collect(entry,receipt):
    if not all(key in entry for key in ('icons','help','resources')):
        return {'schema':1,'available':False,'stage':'Unknown','reason':'This pinned SDK catalog does not expose a qualified resource inventory.'}
    icons=entry['icons'];resources=entry['resources'];help_path=entry['help']
    if not isinstance(icons,list) or not isinstance(resources,list) or len(icons)+len(resources)+(help_path is not None)>64:raise DevelopmentFault('The SDK resource inventory exceeds its bound.')
    declarations=[{'kind':'icon','index':index,'path':path} for index,path in enumerate(icons)]
    if help_path is not None:declarations.append({'kind':'help','index':0,'path':help_path})
    names=set()
    for value in resources:
        if not isinstance(value,str) or ':' not in value:raise DevelopmentFault('The SDK resource declaration has an unsupported shape.')
        name,path=value.split(':',1)
        if not 1<=len(name)<=63 or any(not 0x21<=ord(c)<=0x7e or c in '/\\:' for c in name) or name.lower() in names:raise DevelopmentFault('Resource names must be unique and match the pinned container contract.')
        names.add(name.lower());declarations.append({'kind':'file','name':name,'index':0,'path':path})
    files={value['path']:value for value in receipt['files']};bound=[]
    for declaration in declarations:
        path=relative(declaration['path'])
        value=files.get(path)
        if not value:raise DevelopmentFault('Declared resource '+path+' is missing or excluded from the captured source. Include its real project file before building.')
        bound.append({**declaration,'bytes':value['bytes'],'sha256':value['sha256']})
    selected={value['path'] for value in bound}
    unregistered=[value['path'] for value in receipt['files'] if value['path'].split('/')[0].casefold()=='assets' and value['path'] not in selected]
    return {'schema':1,'available':True,'stage':'Registered','sourceSha256':receipt['sha256'],'manifestSha256':receipt['manifestSha256'],'entries':bound,
        'unregisteredAssets':unregistered[:64],'unregisteredCount':len(unregistered),'consumerVerified':False,'embeddedVerified':False,'guestVerified':False}
