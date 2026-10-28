"""Real bounded decoders and private owned uploads, without model inference."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch
import uuid
from PIL import Image
import test_runs
from attachment_store import Attachments,MAX_FILE
from session_store import encode
from store import ProjectFault


class Uploads(unittest.TestCase):
    setUp=test_runs.Runs.setUp
    tearDown=test_runs.Runs.tearDown
    open=test_runs.Runs.open

    def upload_data(self,raw,name='own.txt',rid=None):
        return {'requestId':rid or str(uuid.uuid4()),'name':name,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mediaType':'application/octet-stream'}

    def image(self,kind='PNG',size=(3,2)):
        out=io.BytesIO();Image.new('RGB',size,'purple').save(out,kind);return out.getvalue()

    def test_real_png_jpeg_webp_decoded_fully_private_and_upload_never_admits_run(self):
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            for kind,suffix,mime in [('PNG','png','image/png'),('JPEG','jpg','image/jpeg'),('WEBP','webp','image/webp')]:
                raw=self.image(kind);result=attachments.upload(self.upload_data(raw,'Display 😀.'+suffix),io.BytesIO(raw))
                self.assertEqual(result['state'],'ready',result);metadata=result['attachment']
                self.assertEqual((metadata['width'],metadata['height']),(3,2));self.assertEqual(metadata['mediaType'],mime)
                path=attachments.root()/metadata['id']/('original.'+suffix)
                self.assertEqual(path.read_bytes(),raw);self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
                self.assertNotIn(str(self.root),encode(result));self.assertNotIn('path',metadata)
            self.assertEqual(len(attachments.listing()['attachments']),3)
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
            self.assertEqual(list(store.workspace.iterdir()),[store.workspace/'module.R4MF'])

    def test_text_sources_unicode_and_svg_html_are_inert_text(self):
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            for name,text in [('own.rs','fn main() {} // 😀'),('own.svg','<svg onload="alert(1)"/>'),('own.html','<script>alert(1)</script>')]:
                raw=text.encode();result=attachments.upload(self.upload_data(raw,name),io.BytesIO(raw))
                self.assertEqual(result['state'],'ready');self.assertEqual(result['attachment']['mediaType'],'text/plain')
                self.assertEqual(result['attachment']['mode'],'text')

    def test_same_original_upload_receipt_survives_reopen_and_changed_body_conflicts(self):
        raw=self.image();data=self.upload_data(raw,'own.png')
        with self.open() as store:result=Attachments(store,self.sid).upload(data,io.BytesIO(raw))
        with self.open() as store:
            attachments=Attachments(store,self.sid);self.assertEqual(attachments.receipt(data['requestId']),result)
            self.assertEqual(attachments.upload(data,io.BytesIO(raw)),result)
            other=b'changed'
            with self.assertRaises(ProjectFault):attachments.upload(self.upload_data(other,'own.png',data['requestId']),io.BytesIO(other))
            self.assertEqual(len(attachments.listing()['attachments']),1)

    def test_truncated_animated_and_excessive_dimension_images_never_become_ready(self):
        out=io.BytesIO();Image.new('RGB',(2,2),'red').save(out,'PNG',save_all=True,append_images=[Image.new('RGB',(2,2),'blue')],duration=20)
        import struct,zlib
        ihdr=struct.pack('>IIBBBBB',16385,2,8,2,0,0,0);tag=b'IHDR'+ihdr
        huge=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',len(ihdr))+tag+struct.pack('>I',zlib.crc32(tag))
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            for raw in (self.image()[:40],self.image('JPEG')[:80],out.getvalue(),huge):
                result=attachments.upload(self.upload_data(raw,'bad.png'),io.BytesIO(raw))
                self.assertEqual(result['state'],'rejected',result)
            self.assertEqual(attachments.listing()['attachments'],[])

    def test_actual_size_hash_invalid_utf8_and_unsupported_formats_rejected(self):
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            cases=[(self.upload_data(b'ab'),b'a'),({**self.upload_data(b'ab'),'sha256':'0'*64},b'ab'),
                (self.upload_data(b'\xffbad'),b'\xffbad'),(self.upload_data(b'a\x00b'),b'a\x00b'),
                (self.upload_data(b'%PDF-1.7\n','own.pdf'),b'%PDF-1.7\n'),(self.upload_data(b'PKzip','own.zip'),b'PKzip')]
            for data,raw in cases:self.assertEqual(attachments.upload(data,io.BytesIO(raw))['state'],'rejected')
            self.assertFalse(attachments.listing()['attachments'])

    def test_invalid_names_oversize_and_foreign_session_fail_before_file_write(self):
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            for name in ('../escape','dir/escape','dir\\escape','..','bad\0name','\ud800'):
                with self.assertRaises(ProjectFault):attachments.upload(self.upload_data(b'own',name),io.BytesIO(b'own'))
            with self.assertRaises(ProjectFault):attachments.upload({**self.upload_data(b'own'),'size':MAX_FILE+1},io.BytesIO(b'own'))
            with self.assertRaises(ProjectFault):Attachments(store,str(uuid.uuid4()))
            self.assertFalse((store.directory/self.sid/'Attachments').exists())

    def test_remove_draft_hides_card_but_keeps_original_bytes_and_quota(self):
        raw=b'private original'
        with self.open() as store:
            attachments=Attachments(store,self.sid);result=attachments.upload(self.upload_data(raw),io.BytesIO(raw));ident=result['attachment']['id']
            before=attachments.usage();attachments.remove(ident)
            self.assertEqual(attachments.listing()['attachments'],[]);self.assertEqual(attachments.usage(),before)
            self.assertEqual((attachments.root()/ident/'original.txt').read_bytes(),raw)
            with patch('attachment_store.MAX_SESSION',len(raw)):
                with self.assertRaises(ProjectFault):attachments.upload(self.upload_data(b'one'),io.BytesIO(b'one'))
            self.assertEqual(attachments.receipt(result['requestId'])['state'],'removed')

    def test_lost_publication_after_final_rename_stays_unknown_and_charged(self):
        raw=b'original publication';data=self.upload_data(raw)
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            with patch('attachment_store.sync',side_effect=OSError('owned directory fsync loss')):
                result=attachments.upload(data,io.BytesIO(raw))
            self.assertEqual(result['state'],'unknown');self.assertEqual(attachments.usage()['sessionBytes'],len(raw))
            self.assertEqual(attachments.listing()['attachments'],[])
            self.assertEqual(attachments.upload(data,io.BytesIO(raw))['state'],'unknown')
            with self.assertRaises(ProjectFault):attachments.remove(attachments.row(data['requestId'],True)['id'])

    def test_interrupted_transport_and_lost_helper_never_publish_or_replay(self):
        class Broken:
            def read(self,_):raise OSError('owned interrupted stream')
        with self.open() as store:
            attachments=Attachments(store,self.sid)
            self.assertEqual(attachments.upload(self.upload_data(b'one'),Broken())['state'],'rejected')
            class Lost:
                def read(self,_):raise KeyboardInterrupt()
            data=self.upload_data(b'two')
            with self.assertRaises(KeyboardInterrupt):attachments.upload(data,Lost())
            with store.db:store.db.execute('UPDATE session_attachments SET worker=? WHERE request_id=?',(encode({'pid':os.getpid(),'birth':'previous-process-birth'}),data['requestId']))
            self.assertEqual(attachments.receipt(data['requestId'])['state'],'unknown')
            self.assertEqual(attachments.upload(data,io.BytesIO(b'two'))['state'],'unknown')
            self.assertEqual(attachments.listing()['attachments'],[])

    def test_symlink_private_root_never_writes_foreign_folder(self):
        with self.open() as store:
            parent=store.directory/self.sid;parent.mkdir()
            target=self.root/'foreign';target.mkdir();(parent/'Attachments').symlink_to(target,target_is_directory=True)
            with self.assertRaises(ValueError):Attachments(store,self.sid).upload(self.upload_data(b'one'),io.BytesIO(b'one'))
            self.assertEqual(list(target.iterdir()),[])
            self.assertEqual(Attachments(store,self.sid).listing()['attachments'],[])

    def test_other_session_cannot_list_read_receipt_or_remove_known_uuid(self):
        with self.open() as store:
            attachments=Attachments(store,self.sid);result=attachments.upload(self.upload_data(b'own'),io.BytesIO(b'own'))
            second=str(uuid.uuid4());original=store.row(self.sid)
            with store.db:store.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,?,?)',
                (second,self.pid,'Other own session',original['settings'],original['engine'],'now','now'))
            other=Attachments(store,second);self.assertEqual(other.listing()['attachments'],[])
            with self.assertRaises(ProjectFault):other.receipt(result['requestId'])
            with self.assertRaises(ProjectFault):other.remove(result['attachment']['id'])
            self.assertEqual(attachments.receipt(result['requestId']),result)
