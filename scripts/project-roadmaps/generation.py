"""Private, bounded file-generation attestation for previously verified reads."""
from pathlib import Path
import stat
from validation import identity


def signature(info,kind):
    values=[info.st_dev,info.st_ino,info.st_mode,info.st_uid]
    if kind!='directory':values.append(info.st_nlink)
    if kind=='file':values.extend((info.st_size,info.st_mtime_ns,info.st_ctime_ns))
    elif kind=='control':values.append(info.st_size)
    return [str(value) for value in values]


def capture(projects,project_id):
    project_id=identity(project_id);projects=Path(projects).absolute();parent=projects/project_id
    directories=[projects,parent,parent/'Workspace',parent/'Roadmap']
    files=[projects/'Projects.sqlite',parent/'Workspace/module.R4MF',parent/'Roadmap/Roadmap.sqlite']
    candidates=[(path,'directory',False) for path in directories]+[(path,'file',False) for path in files]
    for database in (files[0],files[2]):
        candidates.extend((database.with_name(database.name+suffix),'control' if suffix=='-shm' else 'file',True) for suffix in ('-journal','-wal','-shm'))
    result=[]
    try:
        for path,kind,optional in candidates:
            try:info=path.lstat()
            except FileNotFoundError:
                if optional:result.append({'path':str(path),'kind':kind,'signature':None});continue
                return None
            if path.resolve(strict=True)!=path or (not stat.S_ISDIR(info.st_mode) if kind=='directory' else not stat.S_ISREG(info.st_mode) or info.st_nlink!=1):return None
            result.append({'path':str(path),'kind':kind,'signature':signature(info,kind)})
        return result
    except OSError:return None
