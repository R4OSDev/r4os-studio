"""Owned pending-upload delegation, real decoders and preserved original receipts."""
import asyncio
from contextlib import closing
import hashlib
import io
import os
import subprocess
import unittest
from unittest.mock import patch
import uuid

from PIL import Image
from attachment_decode import decode_pending, request_decode
from attachment_store import Attachments, decode_image
from host import Host
from profile import SKILL_PROFILE
from session_store import SessionStore, encode
from skill_application import packages
from store import ProjectFault
from test_document_inputs import pdf
import test_runs


class AttachmentDecodeTests(unittest.IsolatedAsyncioTestCase):
    setUp = test_runs.Runs.setUp
    tearDown = test_runs.Runs.tearDown
    open = test_runs.Runs.open

    def host(self):
        return Host({'projects':str(self.projects),'r4os':str(self.r4os),
                     'providers':str(self.providers),'uid':os.getuid()})

    def image(self):
        out=io.BytesIO();Image.new('P',(32,32),0).save(out,'PNG');return out.getvalue()

    def upload_data(self,raw,name):
        return {'requestId':str(uuid.uuid4()),'name':name,'mediaType':'application/octet-stream',
                'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}

    async def test_real_socket_decodes_project_and_skill_pending_png_and_pdf_without_run(self):
        host=self.host();path=str(self.root/'decoder.sock')
        server=await asyncio.start_unix_server(host.connection,path=path)
        skill=str(uuid.uuid4());sid=str(uuid.uuid4())
        with closing(packages.connect(self.root/'Skills')) as db:
            packages.create(db,self.root/'Skills',{'id':skill,'name':'Owned decoder fixture'})
        with closing(SessionStore(self.projects,self.r4os,skill,'skill')) as store,store.db:
            store.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,NULL,1,'now','now')",
                (sid,skill,'Owned session',encode(self.settings),encode({'profile':SKILL_PROFILE})))
        def upload(kind,owner,sid,raw,name):
            with closing(SessionStore(self.projects,self.r4os,owner,kind)) as store:
                decoder=lambda ident:request_decode(store,sid,ident,path)
                attachments=Attachments(store,sid,decoder);data=self.upload_data(raw,name)
                result=attachments.upload(data,io.BytesIO(raw))
                self.assertEqual(result['state'],'ready',result)
                self.assertEqual(attachments.receipt(data['requestId']),result)
                suffix='png' if name.endswith('png') else 'pdf'
                self.assertEqual((attachments.root()/result['attachment']['id']/('original.'+suffix)).read_bytes(),raw)
                self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
                self.assertFalse(store.db.execute('SELECT 1 FROM items').fetchone())
                return result
        try:
            for kind,owner,session in [('project',self.pid,self.sid),('skill',skill,sid)]:
                png=await asyncio.to_thread(upload,kind,owner,session,self.image(),'own.png')
                self.assertEqual((png['attachment']['width'],png['attachment']['height']),(32,32))
                document=await asyncio.to_thread(upload,kind,owner,session,pdf('Owned delegated text'),'own.pdf')
                self.assertTrue(document['attachment']['readable'])
        finally:
            server.close();await server.wait_closed()
        self.assertEqual(host.attachment_decodes,0)

    async def test_no_arbitrary_path_foreign_session_changed_bytes_or_completed_receipt(self):
        host=self.host();raw=self.image();data=self.upload_data(raw,'own.png');requests=[]
        with self.open() as store:
            def decoder(ident):
                request={'operation':'decode_pending_attachment','projects':str(self.projects),
                         'ownerType':'project','ownerId':self.pid,'sessionId':self.sid,'attachmentId':ident}
                requests.append(request)
                for extra in ({'path':'/etc/passwd'},{'command':'true'}, {'projects':str(self.root/'Other')},
                              {'sessionId':str(uuid.uuid4())},{'ownerId':str(uuid.uuid4())}):
                    with self.assertRaises(ProjectFault):decode_pending(host,{**request,**extra})
                path=Attachments(store,self.sid).root()/ident/'original.uploading'
                path.write_bytes(b'changed')
                with self.assertRaises(ProjectFault):decode_pending(host,request)
                path.write_bytes(raw)
                result=decode_pending(host,request)
                path.unlink();path.symlink_to(self.root/'foreign.png')
                (self.root/'foreign.png').write_bytes(raw)
                with self.assertRaises((ValueError,ProjectFault)):decode_pending(host,request)
                path.unlink();path.write_bytes(raw)
                return result
            result=Attachments(store,self.sid,decoder).upload(data,io.BytesIO(raw))
            self.assertEqual(result['state'],'ready',result)
            with self.assertRaises(ProjectFault):decode_pending(host,requests[0])
            self.assertEqual(Attachments(store,self.sid).receipt(data['requestId']),result)

    async def test_failed_service_never_falls_back_replays_or_blames_image_dimensions(self):
        host=self.host();host.attachment_decodes=1
        with self.assertRaises(ProjectFault) as busy:
            await host.handle({'operation':'decode_pending_attachment'})
        self.assertEqual(busy.exception.code,429)
        self.assertEqual(host.attachment_decodes,1)
        raw=self.image();data=self.upload_data(raw,'own.png')
        with self.open() as store:
            decoder=lambda ident:request_decode(store,self.sid,ident,str(self.root/'absent.sock'))
            with patch('attachment_store.decode_image',side_effect=AssertionError('No local fallback')):
                result=Attachments(store,self.sid,decoder).upload(data,io.BytesIO(raw))
                self.assertEqual(result['state'],'rejected')
                self.assertIn('Studio service problem',result['reason'])
                self.assertNotIn('16384',result['reason'])
                self.assertEqual(Attachments(store,self.sid,decoder).upload(data,io.BytesIO(raw)),result)
            self.assertEqual(Attachments(store,self.sid).listing()['attachments'],[])
            self.assertFalse(store.db.execute('SELECT 1 FROM runs').fetchone())
        image_path=self.root/'own.png';image_path.write_bytes(raw)
        with patch('attachment_store.subprocess.run',return_value=subprocess.CompletedProcess([],1,b'')):
            with self.assertRaises(ProjectFault) as fault:decode_image(image_path)
            self.assertEqual(fault.exception.code,503)


if __name__=='__main__':unittest.main()
