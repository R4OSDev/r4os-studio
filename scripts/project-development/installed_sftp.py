"""Read-only native SFTP access to exact targets from the immutable package manifest."""
from contracts import DevelopmentFault,LIMITS
from inbox_sftp import InboxSftp,Reader,RemoteStatus,string,u32
from update_plans import target
import stat

class InstalledRead(InboxSftp):
    def __init__(self,ssh,payloads,guard=lambda:None):
        super().__init__(ssh,guard)
        self.paths={}
        for payload in payloads:
            canonical=target(payload['canonicalTarget'])
            if canonical!=payload['component']['target']:raise DevelopmentFault('The immutable component target differs.')
            self.paths['/C'+canonical]=payload['file']['bytes']
    def path(self,value):
        if value not in self.paths:raise DevelopmentFault('Read only an exact installed target from the frozen update package.',400)
        return value
    async def stat(self,path):
        self.path(path)
        try:kind,reader=await self.request(17,string(path))
        except RemoteStatus as error:
            if error.remote_code==2:return None
            raise
        if kind!=105:raise DevelopmentFault('Installed target STAT has no native attributes.')
        flags=reader.number();value={}
        if flags&~15:raise DevelopmentFault('Unsupported installed target attributes.')
        if flags&1:value['bytes']=reader.wide()
        if flags&2:reader.number();reader.number()
        if flags&4:value['mode']=reader.number()
        if flags&8:reader.number();reader.number()
        reader.end()
        if 'bytes' not in value or 'mode' not in value:raise DevelopmentFault('Installed target attributes are incomplete.')
        value['regular']=stat.S_ISREG(value['mode'])
        return value
    async def open(self,path,write=False):
        self.path(path)
        if write:raise DevelopmentFault('Installed artifact verification is read-only.',403)
        kind,reader=await self.request(3,string(path)+u32(1)+u32(0))
        if kind!=102:raise DevelopmentFault('Installed target OPEN has no native read handle.')
        value=reader.text(256);reader.end()
        if not value:raise DevelopmentFault('Installed target read handle is empty.')
        return value
    async def write(self,*args,**kwargs):raise DevelopmentFault('Installed artifact verification is read-only.',403)
    async def put(self,*args,**kwargs):raise DevelopmentFault('Installed artifact verification is read-only.',403)
    async def rename(self,*args,**kwargs):raise DevelopmentFault('Installed artifact verification is read-only.',403)
    async def close(self,handle,write=False):
        if write:raise DevelopmentFault('Installed artifact verification is read-only.',403)
        return await super().close(handle)
