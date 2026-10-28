"""Private session uploads and original receipts; no workspace or model access."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid
from profile import directory,regular
from session_store import encode,identity,now
from store import ProjectFault

MAX_FILE=16*1024*1024
MAX_RUN=32*1024*1024
MAX_FILES=8
MAX_SESSION=256*1024*1024
MAX_OWNER=1024*1024*1024
MAX_SESSION_FILES=256
MAX_OWNER_FILES=2048
TEXT_EXTENSIONS={'txt','md','markdown','json','csv','log','py','js','jsx','ts','tsx','c','h','cpp','hpp','zig','rs',
    'toml','yaml','yml','ini','cfg','r4mf','r4af','html','css','xml','svg','sh','ps1','bat','sql','diff','patch'}


def birth(pid):
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[19]
    except (OSError,IndexError):return None


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def decode_image(path):
    script=Path(__file__).with_name('image_check.py').absolute()
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--cap-drop','ALL']
    for root in ('/usr','/lib','/lib64'):
        if Path(root).exists():args+=['--ro-bind',root,root]
    args+=['--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(regular(path)),'/input',
        '--ro-bind',str(script),'/check.py','--clearenv','--setenv','LANG','C.UTF-8',
        '/usr/bin/python3','-I','-B','/check.py']
    try:
        result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=10,check=False)
        if len(result.stdout)>4096:raise ValueError()
        value=json.loads(result.stdout)
        if result.returncode or 'error' in value:
            if value.get('error') in ('Image dimensions exceed16384 per axis or40 million pixels.',
                                    'Animated images are not supported. Attach one still frame.'):
                raise ProjectFault(value['error'],400)
            raise ValueError()
        if set(value)!={'mediaType','width','height','mode','decoder','transparent'} or value['mediaType'] not in ('image/png','image/jpeg','image/webp'):raise ValueError()
        return {k:v for k,v in value.items() if k!='decoder'}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise ProjectFault('Image validation failed. Use a complete still PNG/JPEG/WebP within16384 pixels per axis and40 million pixels, and install the qualified raster decoder.',400) from None


def decode_pdf(path):
    script=Path(__file__).with_name('pdf_check.py').absolute()
    args=['/usr/bin/bwrap','--die-with-parent','--new-session','--unshare-all','--cap-drop','ALL']
    for root in ('/usr','/lib','/lib64'):
        if Path(root).exists():args+=['--ro-bind',root,root]
    args+=['--dev','/dev','--proc','/proc','--tmpfs','/tmp','--ro-bind',str(regular(path)),'/input',
        '--ro-bind',str(script),'/check.py','--clearenv','--setenv','LANG','C.UTF-8',
        '/usr/bin/python3','-I','-B','/check.py']
    try:
        result=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode or len(result.stdout)>8*1024*1024:raise ValueError()
        value=json.loads(result.stdout)
        if (value.get('mode')!='pdfText' or value.get('mediaType')!='application/pdf' or type(value.get('readable')) is not bool
                or type(value.get('truncated')) is not bool or not isinstance(value.get('_text'),str)
                or len(value['_text'].encode('utf-8'))>2*1024*1024):raise ValueError()
        return value
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise ProjectFault('PDF validation failed or the qualified Poppler25.03.0 decoder is unavailable. Use a valid PDF or UTF-8 text.',400) from None


def inspect(path,name,claimed):
    with regular(path).open('rb') as stream:head=stream.read(16)
    if head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8') or (head[:4]==b'RIFF' and head[8:12]==b'WEBP'):
        return decode_image(path)
    if head.startswith(b'%PDF-'):return decode_pdf(path)
    extension=name.rsplit('.',1)[-1].lower() if '.' in name else ''
    if extension not in TEXT_EXTENSIONS and not (not extension and claimed.startswith('text/')):
        raise ProjectFault('Unsupported attachment. Use PNG/JPEG/WebP, a valid PDF, or UTF-8 text/source files.',400)
    try:
        content=regular(path).read_bytes().decode('utf-8-sig')
        if '\x00' in content:raise ValueError()
    except (UnicodeError,ValueError):raise ProjectFault('Text attachments must contain valid UTF-8 without NUL bytes.',400) from None
    if len(content.encode('utf-8'))>2*1024*1024:raise ProjectFault('Text attachments exceed2 MiB. Attach a smaller document or source excerpt.',400)
    return {'mode':'text','mediaType':'text/plain','extractedBytes':len(content.encode('utf-8')),
        'extractedSha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),'readable':True,'truncated':False}


class Attachments:
    def __init__(self,store,sid):self.store=store;self.sid=identity(sid);store.row(self.sid)

    def exists(self):return self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='session_attachments' AND type='table'").fetchone() is not None

    def schema(self):
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS session_attachments(
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), request_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL, metadata TEXT NOT NULL, state TEXT NOT NULL, reason TEXT,
                worker TEXT NOT NULL, created_at TEXT NOT NULL)''')
            self.store.db.execute('CREATE INDEX IF NOT EXISTS attachment_session ON session_attachments(session_id)')

    def root(self):return directory(directory(self.store.directory/self.sid)/'Attachments')

    def row(self,ident,request=False):
        ident=identity(ident)
        row=self.store.db.execute('SELECT * FROM session_attachments WHERE '+('request_id' if request else 'id')+'=? AND session_id=?',(ident,self.sid)).fetchone() if self.exists() else None
        if not row:raise ProjectFault('Attachment not found in this session.',404)
        return row

    def receipt(self,rid):
        row=self.row(rid,True);state=row['state']
        if state=='pending':
            owner=json.loads(row['worker'])
            if birth(owner['pid'])!=owner['birth']:state='unknown'
        result={'requestId':rid,'state':'removed' if state in ('removing','purged') else state}
        if state=='ready':result['attachment']={**json.loads(row['metadata']),'state':'ready'}
        if row['reason']:result['reason']=row['reason']
        if state=='unknown':result['reason']='The original upload was not confirmed. No attachment was published and no upload was repeated.'
        return result

    def usage(self):
        rows=self.store.db.execute("SELECT session_id,metadata FROM session_attachments WHERE state IN ('pending','unknown','ready','removed','removing')").fetchall() if self.exists() else []
        own=[r for r in rows if r['session_id']==self.sid]
        charged=lambda r:json.loads(r['metadata']).get('storedBytes',json.loads(r['metadata'])['size'])
        return {'sessionBytes':sum(charged(r) for r in own),'ownerBytes':sum(charged(r) for r in rows),
            'sessionFiles':len(own),'ownerFiles':len(rows)}

    def listing(self):
        rows=self.store.db.execute("SELECT metadata FROM session_attachments WHERE session_id=? AND state='ready' ORDER BY rowid",(self.sid,)).fetchall() if self.exists() else []
        try:
            from PIL import features,__version__
            images=__version__=='11.1.0' and features.check('webp')
        except ImportError:images=False
        try:
            pdf=subprocess.run(['/usr/bin/pdftotext','-v'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
            pdf_available=b'pdftotext version 25.03.0' in pdf.stderr
        except (OSError,subprocess.TimeoutExpired):pdf_available=False
        cleaning=self.store.db.execute("SELECT id,metadata FROM session_attachments WHERE session_id=? AND state='removing'",(self.sid,)).fetchall() if self.exists() else []
        return {'attachments':[{**json.loads(r[0]),'state':'ready','referenced':self.used(json.loads(r[0])['id'])} for r in rows],
            'cleanupPending':[{'id':r['id'],'name':json.loads(r['metadata'])['name']} for r in cleaning],
            'limits':{'maxFiles':MAX_FILES,'maxFileBytes':MAX_FILE,'maxRunBytes':MAX_RUN,'maxSessionBytes':MAX_SESSION,
                'maxOwnerBytes':MAX_OWNER,'maxSessionFiles':MAX_SESSION_FILES,'maxOwnerFiles':MAX_OWNER_FILES,
                'maxTextBytes':2*1024*1024,'maxImagePixels':40_000_000,'maxImageDimension':16384,'maxPdfPages':128},
            'supported':{'images':images,'text':True,'pdf':pdf_available},'usage':self.usage()}

    def upload(self,data,stream):
        if set(data)!={'requestId','name','mediaType','size','sha256'}:raise ProjectFault('Unexpected upload fields.',400)
        rid=identity(data['requestId']);name=data['name'];claimed=data['mediaType'];size=data['size'];sha=data['sha256']
        if (not isinstance(name,str) or not 1<=len(name)<=255 or any(0xd800<=ord(c)<=0xdfff for c in name)
                or len(name.encode('utf-8'))>1024 or name in ('.','..')
                or any(c in name for c in '/\\') or any(ord(c)<32 or ord(c)==127 for c in name)
                or not isinstance(claimed,str) or not re.fullmatch(r'[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+',claimed)
                or len(claimed)>120 or type(size) is not int or not 0<size<=MAX_FILE
                or not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha)):
            raise ProjectFault('Invalid filename, type, size or SHA-256 for this upload.',400)
        fingerprint=hashlib.sha256(encode({'sessionId':self.sid,**data}).encode()).hexdigest();self.schema()
        self.store.db.execute('BEGIN IMMEDIATE')
        try:
            previous=self.store.db.execute('SELECT * FROM session_attachments WHERE request_id=?',(rid,)).fetchone()
            if previous:
                if previous['session_id']!=self.sid or previous['fingerprint']!=fingerprint:raise ProjectFault('This upload request ID belongs to another input.',409)
                return self.receipt(rid)
            usage=self.usage()
            if (usage['sessionBytes']+size>MAX_SESSION or usage['ownerBytes']+size>MAX_OWNER
                    or usage['sessionFiles']>=MAX_SESSION_FILES or usage['ownerFiles']>=MAX_OWNER_FILES):
                raise ProjectFault('Attachment storage is full. Existing attachments were preserved.',409)
            if self.store.db.execute('SELECT COUNT(*) FROM session_attachments').fetchone()[0]>=4096:
                raise ProjectFault('This owner reached the upload receipt limit.',409)
            ident=str(uuid.uuid4());stamp=now();meta={'id':ident,'sessionId':self.sid,'name':name,'size':size,'sha256':sha,'createdAt':stamp}
            self.store.db.execute('INSERT INTO session_attachments VALUES (?,?,?,?,?,?,?,?,?)',
                (ident,self.sid,rid,fingerprint,encode(meta),'pending',None,encode({'pid':os.getpid(),'birth':birth(os.getpid())}),stamp))
            self.store.db.commit()
        finally:
            if self.store.db.in_transaction:self.store.db.rollback()
        parent=directory(self.root()/ident);temp=parent/'original.uploading';finalized=False
        try:
            fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);hashed=hashlib.sha256();total=0
            with os.fdopen(fd,'wb') as target:
                while chunk:=stream.read(min(65536,MAX_FILE+1-total)):
                    total+=len(chunk)
                    if total>MAX_FILE:raise ProjectFault('Attachment exceeds16 MiB.',413)
                    target.write(chunk);hashed.update(chunk)
                target.flush();os.fsync(target.fileno())
            if total!=size or hashed.hexdigest()!=sha:raise ProjectFault('The received attachment size or SHA-256 does not match.',400)
            info=inspect(temp,name,claimed);extracted=info.pop('_text',None);meta.update(info)
            if extracted is not None:
                extracted=extracted.encode('utf-8')
                if hashlib.sha256(extracted).hexdigest()!=info['extractedSha256'] or len(extracted)!=info['extractedBytes']:raise ProjectFault('PDF extraction identity changed.',409)
                self.store.db.execute('BEGIN IMMEDIATE')
                try:
                    usage=self.usage()
                    if usage['sessionBytes']+len(extracted)>MAX_SESSION or usage['ownerBytes']+len(extracted)>MAX_OWNER:
                        raise ProjectFault('Attachment storage cannot hold this PDF text. Existing files were preserved.',409)
                    meta['storedBytes']=size+len(extracted)
                    self.store.db.execute('UPDATE session_attachments SET metadata=? WHERE id=?',(encode(meta),ident));self.store.db.commit()
                finally:
                    if self.store.db.in_transaction:self.store.db.rollback()
                text_path=parent/'extracted.txt'
                fd=os.open(text_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                finalized=True  # Derived bytes reserve the original until publication is certain.
                with os.fdopen(fd,'wb') as target:target.write(extracted);target.flush();os.fsync(target.fileno())
            suffix={'image/png':'png','image/jpeg':'jpg','image/webp':'webp','text/plain':'txt','application/pdf':'pdf'}[info['mediaType']]
            os.replace(temp,parent/('original.'+suffix));finalized=True;sync(parent)
            with self.store.db:self.store.db.execute("UPDATE session_attachments SET state='ready',metadata=? WHERE id=?",(encode(meta),ident))
        except Exception as error:
            # This exclusive temporary file is ours; finalized bytes/other IDs
            # are preserved on any uncertainty and never treated as Ready.
            if not finalized and temp.exists() and temp.is_file() and not temp.is_symlink():
                try:temp.unlink();sync(parent)
                except OSError:finalized=True  # A full disk can also prevent confirming cleanup.
            message=str(error) if isinstance(error,ProjectFault) else 'The attachment could not be validated. Existing files were preserved.'
            with self.store.db:self.store.db.execute('UPDATE session_attachments SET state=?,reason=? WHERE id=?',('unknown' if finalized else 'rejected',message,ident))
        return self.receipt(rid)

    def remove(self,ident):
        ident=identity(ident);self.store.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.row(ident)
            if row['state'] in ('pending','unknown'):raise ProjectFault('Reconcile the original upload before removing its draft.',409)
            used=self.used(ident)
            if used:
                if row['state']=='removing':raise ProjectFault('An inconsistent attachment reference needs maintenance. Existing bytes were preserved.',503)
                self.store.db.execute("UPDATE session_attachments SET state='removed' WHERE id=?",(ident,));self.store.db.commit()
                return {'id':ident,'removed':True,'retainedForHistory':True}
            # This lock serializes with admission's atomic Run+reference commit.
            # Durable removing closes new Send admission before filesystem work.
            self.store.db.execute("UPDATE session_attachments SET state='removing' WHERE id=?",(ident,));self.store.db.commit()
        finally:
            if self.store.db.in_transaction:self.store.db.rollback()
        self.purge(row)
        with self.store.db:self.store.db.execute("UPDATE session_attachments SET state='purged',reason=NULL WHERE id=?",(ident,))
        return {'id':ident,'removed':True,'retainedForHistory':False}

    def used(self,ident):
        """Positive references and uncertain old/config/item references all retain bytes."""
        ident=identity(ident)
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='session_messages'").fetchone():
            for row in self.store.db.execute("SELECT frozen FROM session_messages WHERE session_id=? AND state IN ('queued','dispatching','accepted','unknown')", (self.sid,)):
                if any(meta.get('id') == ident for meta in json.loads(row['frozen']).get('attachments', [])): return True
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='attachment_refs'").fetchone():
            rows=self.store.db.execute('SELECT session_id,frozen FROM attachment_refs WHERE attachment_id=?',(ident,)).fetchall()
            for row in rows:
                data=json.loads(row['frozen'])
                if row['session_id']!=self.sid or data.get('id')!=ident or data.get('sessionId')!=self.sid:
                    raise ProjectFault('Attachment ownership metadata needs maintenance. Existing files were preserved.',503)
            if rows:return True
        for table,column in [('runs','config'),('items','payload')]:
            for row in self.store.db.execute('SELECT '+column+' FROM '+table+' WHERE session_id=?',(self.sid,)):
                try:
                    value=json.loads(row[0]);records=value.get('attachments',[])
                    if not isinstance(value,dict) or not isinstance(records,list) or any(not isinstance(v,dict) for v in records):raise ValueError()
                    if any(v.get('id')==ident for v in records):return True
                except (ValueError,TypeError,AttributeError):
                    raise ProjectFault('Attachment references need maintenance. Existing files were preserved.',503) from None
        return False

    def purge(self,row):
        parent=self.store.directory/self.sid/'Attachments'/identity(row['id'])
        if not parent.exists() and not parent.is_symlink():return
        from image_inputs import SUFFIX
        meta=json.loads(row['metadata']);suffix=SUFFIX.get(meta.get('mediaType'))
        allowed={'original.'+suffix} if suffix else set()
        if meta.get('mode')=='pdfText':allowed.add('extracted.txt')
        try:
            if parent.resolve(strict=True)!=parent or not parent.is_dir():raise ValueError()
            # Preserve unfamiliar entries, links, hardlinks or identities. Never
            # traverse a directory tree to infer ownership of unexpected files.
            entries=list(parent.iterdir())
            for path in entries:
                status=path.lstat()
                if (path.name not in allowed or not stat.S_ISREG(status.st_mode) or status.st_nlink!=1 or status.st_uid!=os.getuid()):raise ValueError()
            for path in entries:path.unlink()
            sync(parent);parent.rmdir();sync(parent.parent)
        except (OSError,ValueError):
            raise ProjectFault('Unused upload cleanup is incomplete. Retry removal; the original receipt and quota were retained.',503) from None

    def preview(self,ident):
        return self.access(ident,True)

    def access(self,ident,preview=False):
        row=self.row(ident)
        if row['state']!='ready' and not (row['state']=='removed' and self.used(ident)):
            raise ProjectFault('This attachment is unavailable. Its original receipt was preserved.',409)
        metadata=json.loads(row['metadata'])
        if preview and metadata.get('mode')!='localImage':raise ProjectFault('Only checked raster images have an inline preview.',415)
        from image_inputs import file_path
        path=file_path(self.store,self.sid,metadata)
        # Internal helper response only. The HTTP route streams bytes and never
        # returns this private path in browser JSON or Studio events.
        return {'path':str(path),'attachment':{**metadata,'state':'ready'}}
