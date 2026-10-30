"""Owned native attachment contracts: provenance, order, limits and original echo."""
import asyncio
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch,AsyncMock
import uuid

from PIL import Image
from attachment_store import Attachments
from claude_inputs import content_digest,prepared_input,sha
from claude_messages import acknowledge
from claude_worker import ClaudeWorker
from instructions import compose
from run_store import admit,get_run
from store import ProjectFault
import test_claude_messages as fixtures
from test_document_inputs import pdf


class ClaudeInputs(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ClaudeMessages();self.f.native_model='claude-haiku-5-5';self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.models=[{'id':self.f.native_model,'efforts':['low'],'imageInputs':'supported','inputModalities':['text','image']}]
        self.f.patches.enter_context(patch('session_store.provider_models',return_value=self.models))

    def upload(self,store,raw,name,kind):
        result=Attachments(store,self.f.sid).upload({'requestId':str(uuid.uuid4()),'name':name,'mediaType':kind,
            'size':len(raw),'sha256':sha(raw)},io.BytesIO(raw))
        self.assertEqual(result['state'],'ready');return result['attachment']

    def image(self,store):
        out=io.BytesIO();Image.new('RGB',(4,3),'purple').save(out,'PNG');return self.upload(store,out.getvalue(),'Own image.png','image/png')

    def data(self,ids,text='Own actual user λ input'):
        return {'requestId':str(uuid.uuid4()),'revision':1,'text':text,'attachments':ids,'nativeImageInputs':1,'documentInputs':1}

    def test_order_provenance_native_image_bytes_and_cross_language_digest(self):
        with self.f.open() as store:
            image=self.image(store);doc=self.upload(store,'Own document λ source'.encode(),'own.txt','text/plain')
            data=self.data([doc['id'],image['id']]);run,_=admit(store,self.f.sid,data,self.f.providers)
            config=json.loads(get_run(store,run['id'])['config']);value=prepared_input(store,self.f.sid,run['id'],config)
            self.assertEqual([p['type'] for p in value['content']],['text','text','text','image'])
            self.assertEqual(value['content'][0]['text'],data['text'])
            self.assertEqual(json.loads(value['content'][1]['text'])['id'],doc['id'])
            self.assertEqual(json.loads(value['content'][2]['text'])['sha256'],image['sha256'])
            self.assertEqual(content_digest(value['content']),config['claudeInput']['contentSha256'])
            node="import {pathToFileURL} from 'node:url';import {readFileSync} from 'node:fs';const m=await import(pathToFileURL(process.argv[1]));process.stdout.write(m.contentDigest(JSON.parse(readFileSync(0,'utf8')).content));"
            result=subprocess.run(['/usr/bin/node','--input-type=module','-e',node,str(Path(__file__).with_name('claude_content.mjs'))],input=json.dumps(value).encode(),stdout=subprocess.PIPE,check=True)
            self.assertEqual(result.stdout.decode(),value['contentSha256'])
            self.assertNotEqual(content_digest(list(reversed(value['content']))),value['contentSha256'])
            self.assertNotIn(value['content'][-1]['source']['data'],json.dumps(config))
            self.assertEqual(admit(store,self.f.sid,data,self.f.providers)[1],False)

    def test_pdf_only_is_explicit_extracted_text_with_limitations_and_no_invented_message(self):
        with self.f.open() as store:
            meta=self.upload(store,pdf('Own PDF source'),'own.pdf','application/pdf')
            run,_=admit(store,self.f.sid,self.data([meta['id']],''),self.f.providers)
            config=json.loads(get_run(store,run['id'])['config']);value=prepared_input(store,self.f.sid,run['id'],config)
            block=json.loads(value['content'][0]['text'])
            self.assertEqual(block['mode'],'pdfText');self.assertIn('Own PDF source',block['content'])
            self.assertIn('Embedded images',block['limitation']);self.assertTrue(block['allAvailableTextIncluded'])

    def test_unknown_image_capability_and_long_document_permission_failure_preserve_originals(self):
        with self.f.open() as store:
            meta=self.image(store);self.models[0]['imageInputs']='unknown'
            with self.assertRaises(ProjectFault):admit(store,self.f.sid,self.data([meta['id']]),self.f.providers)
            self.models[0]['imageInputs']='supported'
            doc=self.upload(store,b'x'*9000,'long.txt','text/plain')
            session=store.get(self.f.sid);saved=store.update(self.f.sid,{'revision':session['revision'],'permissions':{**session['permissions'],'studio.read_attachment':False}},self.f.providers)
            data=self.data([doc['id']]);data['revision']=saved['revision']
            with self.assertRaises(ProjectFault):admit(store,self.f.sid,data,self.f.providers)
            self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
            self.assertEqual(len(Attachments(store,self.f.sid).listing()['attachments']),2)

    def test_changed_attachment_is_rejected_before_native_input_preparation(self):
        with self.f.open() as store:
            meta=self.image(store);run,_=admit(store,self.f.sid,self.data([meta['id']]),self.f.providers)
            config=json.loads(get_run(store,run['id'])['config'])
            path=store.directory/self.f.sid/'Attachments'/meta['id']/'original.png';path.write_bytes(b'changed after original Send')
            with self.assertRaises(ProjectFault):prepared_input(store,self.f.sid,run['id'],config)
            self.assertEqual(config['attachments'][0]['sha256'],meta['sha256'])

    def test_structured_original_echo_requires_content_hash_and_never_persists_image_data(self):
        with self.f.open() as store:
            meta=self.image(store);data=self.data([meta['id']]);run,_=admit(store,self.f.sid,data,self.f.providers)
            w=self.f.receiver(store,run);expected=w.config['claudeInput']
            frame={'native':{'type':'user','isReplay':True,'session_id':self.f.native},'identity':{
                'nativeType':'user','nativeSessionId':self.f.native,'nativeInputRequestIds':[w.row['request_id']],
                'nativeMessageId':w.row['request_id'],'nativeInputReceiptKind':'stdinEcho',
                'nativeInputTextSha256':expected['textSha256']}}
            with self.assertRaises(ProjectFault):acknowledge(w,frame)
            self.assertFalse(w.input_receipt.is_set())
            frame['identity']['nativeInputContentSha256']=expected['contentSha256']
            self.assertTrue(acknowledge(w,frame));self.assertTrue(acknowledge(w,frame))
            payload=json.loads(store.db.execute('SELECT payload FROM claude_input_receipts').fetchone()[0])
            self.assertEqual(payload['kind'],'original-content');self.assertEqual(payload['binding']['nativeContentSha256'],expected['contentSha256'])
            self.assertNotIn('base64',json.dumps(payload))

    def test_frozen_global_project_and_skill_sources_have_explicit_native_hash(self):
        with self.f.open() as store:
            run,_=admit(store,self.f.sid,{'requestId':str(uuid.uuid4()),'revision':1,'text':'Own instruction source check','skillSelection':1},self.f.providers)
            config=json.loads(get_run(store,run['id'])['config']);prompt=compose(config)
            self.assertIn('GLOBAL R4OS STUDIO INSTRUCTIONS',prompt);self.assertIn('PROJECT INSTRUCTIONS FROM Workspace/Agents.md',prompt)
            self.assertIn('CURRENT STUDIO GLOBAL SKILLS',prompt)
            self.assertEqual(config['claudeInstructions']['sha256'],sha(prompt.encode()))
            self.assertEqual(config['claudeInstructions']['bytes'],len(prompt.encode()))
            changed=copy.deepcopy(config);changed['projectInstructions']['text']+=' altered source'
            with self.assertRaises(ProjectFault):compose(changed)

    def test_screenshot_delivery_uses_bound_original_evidence_and_explicit_image_capability(self):
        image={'id':str(uuid.uuid4()),'jobId':str(uuid.uuid4()),'projectId':self.f.pid,'kind':'screenshot'}
        original={'metadata':image,'base64':'YWJj'}
        w=SimpleNamespace(config={'permissions':{'studio.capture_vm':True},'claudeModel':{'imageInput':'supported'}},
            manifest={'projectId':self.f.pid},development=SimpleNamespace(request=AsyncMock(return_value=original)))
        result={'success':True,'image':image,'output':'Original screenshot retained.'}
        output=asyncio.run(ClaudeWorker.mcp_output(w,result))
        self.assertEqual(output['content'][-1],{'type':'image','mimeType':'image/png','data':'YWJj'})
        self.assertNotIn('YWJj',output['content'][0]['text'])
        changed={'metadata':{**image,'projectId':str(uuid.uuid4())},'base64':'YWJj'}
        with self.assertRaises(ValueError):asyncio.run(ClaudeWorker.mcp_output(w,result,changed))
        w.config['permissions']['studio.capture_vm']=False
        self.assertTrue(asyncio.run(ClaudeWorker.mcp_output(w,result,original))['isError'])
        w.config['claudeModel']['imageInput']='unknown'
        output=asyncio.run(ClaudeWorker.mcp_output(w,result,original))
        self.assertTrue(all(p['type']=='text' for p in output['content']))
        self.assertIn('does not confirm visual inspection',output['content'][-1]['text'])

    def test_queued_content_keeps_original_echo_when_later_response_frames_arrive(self):
        from message_store import Messages
        from claude_messages import validate_queue
        with self.f.open() as store:
            meta=self.image(store);data=self.data([meta['id']]);message={k:v for k,v in data.items() if k not in ('nativeImageInputs','documentInputs')};message['mode']='queue'
            Messages(store).accept(self.f.sid,message,self.f.providers,{'nativeImageInputs':1,'documentInputs':1})
            frozen=json.loads(Messages(store).row(self.f.sid,message['requestId'])['frozen']);validate_queue(store,self.f.sid,frozen)
            run,_=admit(store,self.f.sid,frozen['runInput'],self.f.providers,None,frozen['config']);w=self.f.receiver(store,run)
            echo={'native':{'type':'user','isReplay':True,'session_id':self.f.native},'identity':{
                'nativeType':'user','nativeSessionId':self.f.native,'nativeInputRequestIds':[w.row['request_id']],
                'nativeMessageId':w.row['request_id'],'nativeInputReceiptKind':'stdinEcho',
                'nativeInputTextSha256':w.config['claudeInput']['textSha256'],
                'nativeInputContentSha256':w.config['claudeInput']['contentSha256']}}
            response=copy.deepcopy(echo);response['native']={'type':'assistant','session_id':self.f.native}
            response['identity'].update(nativeType='assistant',nativeMessageId=str(uuid.uuid4()),providerMessageId='own-content-response')
            for key in ('nativeInputReceiptKind','nativeInputTextSha256','nativeInputContentSha256'):response['identity'].pop(key)
            with self.assertRaises(ProjectFault):acknowledge(w,response)
            self.assertTrue(acknowledge(w,echo))
            original=store.db.execute('SELECT payload FROM claude_input_receipts').fetchone()[0]
            self.assertTrue(acknowledge(w,response))
            self.assertEqual(store.db.execute('SELECT payload FROM claude_input_receipts').fetchone()[0],original)
            self.assertEqual(Messages(store).receipt(self.f.sid,message['requestId'])['state'],'accepted')

    def test_image_size_limits_refuse_before_admission_and_keep_every_uploaded_original(self):
        def noisy(width,height):
            out=io.BytesIO();Image.frombytes('RGB',(width,height),os.urandom(width*height*3)).save(out,'PNG');return out.getvalue()
        with self.f.open() as store:
            large=self.upload(store,noisy(2048,1024),'large.png','image/png')
            with self.assertRaises(ProjectFault) as failure:admit(store,self.f.sid,self.data([large['id']]),self.f.providers)
            self.assertIn('at most4 MiB',str(failure.exception))
            raw=noisy(1024,1024);images=[self.upload(store,raw,'small-'+str(i)+'.png','image/png') for i in range(3)]
            with self.assertRaises(ProjectFault) as failure:admit(store,self.f.sid,self.data([m['id'] for m in images]),self.f.providers)
            self.assertIn('8 MiB',str(failure.exception))
            self.assertEqual(store.db.execute('SELECT count(*) FROM runs').fetchone()[0],0)
            self.assertEqual(len(Attachments(store,self.f.sid).listing()['attachments']),4)
