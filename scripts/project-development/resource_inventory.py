"""Bounded R4M0/1 resource payload readback AFTER the pinned official inspector."""
import hashlib
import mmap
import os
from pathlib import Path
import stat
import struct
from contracts import DevelopmentFault,LIMITS,digest,relative


def inspect(binary,inputs,source):
    if not inputs.get('available'):
        return {'schema':1,'available':False,'stage':'Unknown','reason':inputs.get('reason'),'guestVerified':False,'consumerVerified':False}
    fd=os.open(binary,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or not 64<=st.st_size<=LIMITS['packageBytes']:raise ValueError()
        with mmap.mmap(fd,0,access=mmap.ACCESS_READ) as data:
            if data[:4]!=b'R4M0' or struct.unpack_from('<HH',data,4)!=(1,1) or struct.unpack_from('<H',data,10)[0]!=64:raise ValueError()
            offset,count=struct.unpack_from('<II',data,16)
            if not 1<=count<=64 or offset<64 or offset+count*32>len(data):raise ValueError()
            sections=[]
            for index in range(count):
                name,flags,start,size,memory,alignment,reserved=struct.unpack_from('<8s6I',data,offset+32*index)
                if name.rstrip(b'\0')==b'.rsrc':
                    if flags or start<64 or size<4 or start+size>len(data):raise ValueError()
                    sections.append((start,size))
            if len(sections)>1:raise ValueError()
            entries=[];ranges=[]
            if sections:
                base,size=sections[0];number=struct.unpack_from('<I',data,base)[0];directory_end=4+16*number
                if not 1<=number<=64 or directory_end>size:raise ValueError()
                for index in range(number):
                    kind,ordinal,name_offset,position,length=struct.unpack_from('<HHIII',data,base+4+16*index)
                    if kind not in (1,2,3) or position<directory_end or position%16 or not length or position+length>size:raise ValueError()
                    if any(position<end and start<position+length for start,end in ranges):raise ValueError()
                    ranges.append((position,position+length));name=None
                    if kind==3:
                        if not directory_end<=name_offset<position:raise ValueError()
                        name_end=data.find(b'\0',base+name_offset,min(base+name_offset+64,base+position))
                        if name_end<0:raise ValueError()
                        name=data[base+name_offset:name_end].decode('ascii')
                        if not name or any(not 0x21<=ord(c)<=0x7e or c in '/\\:' for c in name):raise ValueError()
                    elif name_offset:raise ValueError()
                    key=('icon','help','file')[kind-1]
                    actual={'kind':key,'index':ordinal,**({'name':name} if name is not None else {}),'bytes':length,
                        'sha256':hashlib.sha256(data[base+position:base+position+length]).hexdigest()}
                    entries.append(actual)
            expected=inputs['entries']
            if len(expected)!=len(entries):raise DevelopmentFault('The finished artifact resource count differs from the SDK manifest.')
            bound=[]
            for wanted,actual in zip(expected,entries):
                if any(actual.get(key)!=wanted.get(key) for key in ('kind','index','name')):raise DevelopmentFault('The finished artifact resource identity/order differs from the SDK manifest.')
                path=source/relative(wanted['path'])
                if path.resolve(strict=True)!=path or path.stat().st_size!=wanted['bytes'] or digest(path)!=wanted['sha256']:raise DevelopmentFault('A captured resource changed before artifact readback.')
                payload=path.read_bytes();transform=None
                if wanted['kind']=='help' and payload.startswith(b'\xef\xbb\xbf'):payload=payload[3:];transform='SDK HELP strips UTF-8 BOM'
                if actual['bytes']!=len(payload) or actual['sha256']!=hashlib.sha256(payload).hexdigest():raise DevelopmentFault('The finished artifact resource payload differs from its captured source.')
                bound.append({**actual,'path':wanted['path'],'sourceSha256':wanted['sha256'],**({'transform':transform} if transform else {})})
            return {'schema':1,'available':True,'stage':'Embedded','artifactSha256':hashlib.sha256(data).hexdigest(),'sourceSha256':inputs['sourceSha256'],
                'manifestSha256':inputs['manifestSha256'],'container':'R4M0/1','reader':'studio-r4m0-resource-v1','entries':bound,'embeddedVerified':True,'consumerVerified':False,'guestVerified':False}
    except (ValueError,UnicodeError,struct.error,OSError):raise DevelopmentFault('The finished artifact resource payload could not be read within the qualified R4M0 contract.') from None
    finally:os.close(fd)
