"""Owner/session-bound immutable image receipts; native bytes never enter Studio events."""
import base64
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import uuid
from attachment_store import decode_image,sync
from profile import directory,regular
from session_store import encode,identity,now
from store import ProjectFault

MAX_IMAGE=16*1024*1024
MAX_SESSION=256*1024*1024
MAX_OWNER=1024*1024*1024
MAX_IMAGES=128
MAX_RUN_IMAGES=8
RPC_IMAGE_LIMIT=24*1024*1024

class GeneratedImages:
    def __init__(self,store,sid):self.store=store;self.sid=identity(sid);store.row(self.sid)
    def exists(self):return self.store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_images'").fetchone() is not None
    def schema(self):
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS generated_images(
                id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),run_id TEXT NOT NULL REFERENCES runs(id),
                thread_id TEXT NOT NULL,item_id TEXT NOT NULL,metadata TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(session_id,thread_id,item_id))''')
    def root(self):return directory(directory(self.store.directory/self.sid)/'GeneratedImages')
    def native_root(self):return directory(self.root()/'Native')
    def rows(self):
        return self.store.db.execute('SELECT * FROM generated_images WHERE session_id=? ORDER BY created_at,id',(self.sid,)).fetchall() if self.exists() else []
    def list(self):return [json.loads(row['metadata']) for row in self.rows()]
    def get(self,ident):
        ident=identity(ident)
        row=self.store.db.execute('SELECT * FROM generated_images WHERE id=? AND session_id=?',(ident,self.sid)).fetchone() if self.exists() else None
        if not row:raise ProjectFault('Generated image not found in this session.',404)
        return json.loads(row['metadata'])
    def path(self,ident):
        meta=self.get(ident);path=regular(self.root()/(ident+'.image'));st=path.stat()
        if st.st_nlink!=1 or st.st_uid!=os.getuid() or st.st_size!=meta['size'] or not 0<st.st_size<=MAX_IMAGE or hashlib.sha256(path.read_bytes()).hexdigest()!=meta['sha256']:
            raise ProjectFault('The original generated image is missing or changed. It was preserved and was not regenerated.',409)
        return path
    def check_capacity(self,run_id=None):
        rows=self.rows();own=0
        for path in self.root().iterdir():
            if path.name=='Native':continue
            if path.suffix not in ('.image','.pending'):raise ProjectFault('Unexpected private image storage entry.',409)
            path=regular(path);st=path.stat();own+=st.st_size
            if st.st_nlink!=1 or st.st_uid!=os.getuid() or not 0<st.st_size<=MAX_IMAGE:raise ProjectFault('An original image requires storage review.',409)
        if len(rows)>=MAX_IMAGES or own>=MAX_SESSION:raise ProjectFault('Generated-image session storage is full. No new image was requested.',413)
        if run_id and sum(row['run_id']==run_id for row in rows)>=MAX_RUN_IMAGES:raise ProjectFault('This run reached its eight-image limit. Reuse confirmed outputs; no automatic retry.',413)
        # Native save files are separate from validated originals, including unknown outcomes.
        total=0;count=0
        root=self.native_root()
        for parent,dirs,files in os.walk(root,followlinks=False):
            if len(dirs)>128:raise ProjectFault('Native image storage requires review.',413)
            for name in dirs:
                if (Path(parent)/name).is_symlink():raise ProjectFault('Unexpected native image storage link.',409)
            for name in files:
                path=regular(Path(parent)/name);st=path.stat();count+=1;total+=st.st_size
                if st.st_nlink!=1 or st.st_uid!=os.getuid() or st.st_size>MAX_IMAGE or count>MAX_IMAGES or total>MAX_SESSION:
                    raise ProjectFault('Native image storage reached its limit. Original files were retained; generation is disabled until review.',413)
        all_rows=self.store.db.execute('SELECT metadata FROM generated_images').fetchall() if self.exists() else []
        if sum(json.loads(row[0])['size'] for row in all_rows)>=MAX_OWNER:raise ProjectFault('Owner image storage is full.',413)
        return own,sum(json.loads(row[0])['size'] for row in all_rows)
    def accept(self,run_id,thread_id,native):
        ident=native.get('id')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',ident) or not isinstance(thread_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',thread_id):raise ProjectFault('Invalid native image item identity.',400)
        row=self.store.db.execute('SELECT session_id FROM runs WHERE id=?',(run_id,)).fetchone()
        if not row or row[0]!=self.sid:raise ProjectFault('This image belongs to another run.',403)
        raw=native.get('result');saved=native.get('savedPath')
        if saved is not None:
            expected=PurePosixPath('/codex/generated_images')/thread_id/(ident+'.png')
            if not isinstance(saved,str) or PurePosixPath(saved)!=expected or saved!=str(expected):raise ProjectFault('Native image output is outside the private session output path.',409)
        if not isinstance(raw,str) or not raw or len(raw)>4*((MAX_IMAGE+2)//3):raise ProjectFault('Native image data is missing or exceeds16 MiB. The native history was preserved.',413)
        try:data=base64.b64decode(raw,validate=True)
        except ValueError:raise ProjectFault('Native image data is not valid Base64.',400) from None
        if not 0<len(data)<=MAX_IMAGE:raise ProjectFault('Native image exceeds16 MiB.',413)
        hashed=hashlib.sha256(data).hexdigest()
        self.schema()
        previous=self.store.db.execute('SELECT metadata FROM generated_images WHERE session_id=? AND thread_id=? AND item_id=?',(self.sid,thread_id,ident)).fetchone()
        if previous:
            meta=json.loads(previous[0])
            if meta['sha256']!=hashed:raise ProjectFault('The original image item changed its bytes. Both native records were preserved.',409)
            self.path(meta['id']);return meta
        own,total=self.check_capacity(run_id)
        if own+len(data)>MAX_SESSION or total+len(data)>MAX_OWNER:raise ProjectFault('Generated image storage limit reached; original native data retained.',413)
        image_id=str(uuid.uuid5(uuid.UUID(self.sid),thread_id+':'+ident));root=self.root();path=root/(image_id+'.image');temporary=root/(image_id+'.pending')
        created_temporary=False
        try:
            if temporary.exists():
                if regular(temporary).stat().st_nlink!=1 or temporary.read_bytes()!=data:raise ProjectFault('A pending original image requires review.',409)
            else:
                created_temporary=True
                with temporary.open('xb') as file:
                    os.fchmod(file.fileno(),0o600);file.write(data);file.flush();os.fsync(file.fileno())
            decoded=decode_image(temporary)
            # The qualified native image tool returns a PNG, never an executable or polyglot extension.
            if decoded['mediaType']!='image/png':raise ProjectFault('The native image output is not a validated PNG.',400)
            meta={'id':image_id,'sessionId':self.sid,'runId':run_id,'threadId':thread_id,'itemId':ident,
                'sha256':hashed,'size':len(data),'mediaType':decoded['mediaType'],'width':decoded['width'],'height':decoded['height'],
                'transparent':decoded.get('transparent',False),'createdAt':now()}
            if path.exists():
                if regular(path).stat().st_nlink!=1 or path.read_bytes()!=data:raise ProjectFault('The original published image requires review.',409)
                temporary.unlink()
            else:os.rename(temporary,path)
            sync(root)
            with self.store.db:
                self.store.db.execute('INSERT INTO generated_images VALUES(?,?,?,?,?,?,?)',(image_id,self.sid,run_id,thread_id,ident,encode(meta),meta['createdAt']))
            return meta
        except Exception:
            # A fully published orphan is retained for read-only reconciliation, never regenerated.
            if created_temporary and temporary.exists():temporary.unlink()
            raise

def presentation(worker,native,completed):
    ident=native.get('id')
    if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',ident):raise ProjectFault('Invalid native image identity.',400)
    value={'id':ident,'runId':worker.run_id,'type':'tool','tool':'image_gen.imagegen','status':'running','output':'Generating an image…'}
    if not completed:
        GeneratedImages(worker.store,worker.session_id).check_capacity(worker.run_id);return value
    if native.get('status')!='completed':
        failure=native.get('failure');limit=isinstance(failure,dict) and failure.get('type')=='usageLimitExceeded'
        value.update(status='failed',error='usageLimitExceeded' if limit else 'generationFailed',output='Image generation reached its usage limit.' if limit else 'Image generation did not return a confirmed image. No automatic retry.');return value
    meta=GeneratedImages(worker.store,worker.session_id).accept(worker.run_id,worker.thread_id,native)
    value.update(status='completed',output=encode({'image':meta,'stage':'Generated','next':'Use studio.list_generated_images, then import the chosen image into Assets. Generation alone does not embed an R4X resource.'}),generatedImage=meta)
    return value
