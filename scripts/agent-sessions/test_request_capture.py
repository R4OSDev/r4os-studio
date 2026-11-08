"""Exact wire originals, bounded private retention and truthful send evidence."""
import asyncio
import base64
import io
import hashlib
import json
import zlib
import unittest
import uuid
from unittest.mock import patch

from model_transport import ModelTransport, dumps
from model_operations import Operations
from request_capture import body, capture, exists
from run_store import admit
from session_budgets import total
from session_delete import selections
from session_store import encode
from store import ProjectFault
import test_runs as fixtures


class CaptureFixture:
    def setUp(self):
        self.fixture=fixtures.Runs();self.fixture.setUp();self.addCleanup(self.fixture.tearDown);self.addCleanup(self.fixture.doCleanups)
        self.store=self.enterContext(self.fixture.open());self.sid=self.fixture.sid
        self.run,_=admit(self.store,self.sid,self.fixture.data,self.fixture.providers)
        config=json.loads(self.store.db.execute('SELECT config FROM runs WHERE id=?',(self.run['id'],)).fetchone()[0])
        config['apiProvider']={'id':self.fixture.provider,'kind':'local','revision':1,'credentialRevision':0,'protocol':'responses'}
        with self.store.db:self.store.db.execute('UPDATE runs SET config=? WHERE id=?',(encode(config),self.run['id']))
        self.operations=Operations(self.store)

    def operation(self,purpose='conversation'):
        rid=str(uuid.uuid4());self.operations.begin(self.run['id'],rid,purpose=purpose)
        return rid,self.operations.row(rid)[1]

    def capture(self,raw='{"model":"own-model","input":"Own original 雪"}',purpose='conversation'):
        rid,op=self.operation(purpose)
        capture(self.store,op,raw,{'model':'own-model','protocol':'responses','contextWindow':1000000},
                {'schema':3,'enabled':True,'budgetTokens':250000,'globalRevision':7})
        return rid,raw.encode()

class RequestCapture(CaptureFixture,unittest.IsolatedAsyncioTestCase):
    async def test_wire_three_protocols_actual_node_and_exact_original(self):
        received=[]
        async def handle(reader,writer):
            head=(await reader.readuntil(b'\r\n\r\n')).decode()
            length=int(next(x.split(':',1)[1] for x in head.splitlines() if x.lower().startswith('content-length:')))
            raw=await reader.readexactly(length);received.append(raw)
            if '/messages' in head.splitlines()[0]:
                events=[{'type':'message_start','message':{'id':'own','model':'own-model','role':'assistant','content':[],
                    'usage':{'input_tokens':10,'cache_read_input_tokens':2,'cache_creation_input_tokens':3}}},
                    {'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':0}}, {'type':'message_stop'}]
                payload=''.join('data: '+dumps(v)+'\n\n' for v in events)
            elif '/chat/completions' in head.splitlines()[0]:
                payload='data: '+dumps({'id':'own','model':'own-model','choices':[{'index':0,'delta':{'content':'OK'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':10,'completion_tokens':1}})+'\n\ndata: [DONE]\n\n'
            else:
                payload='data: '+dumps({'type':'response.completed','response':{'id':'own','model':'own-model','status':'completed','output':[],
                    'usage':{'input_tokens':10,'output_tokens':0}}})+'\n\n'
            payload=payload.encode();writer.write(f'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n'.encode()+payload)
            await writer.drain();writer.close();await writer.wait_closed()
        server=await asyncio.start_server(handle,'127.0.0.1',0);self.addAsyncCleanup(server.wait_closed);self.addCleanup(server.close)
        for protocol in ('responses','messages','chat-completions'):
            model=ModelTransport({'kind':'local','baseUrl':f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1',
                'auth':'none','protocol':protocol,'contextWindow':1000000,'thinkingDisabled':True},'own-model',chat_policy={'reasoning':'none'})
            model.context_policy={'schema':3,'enabled':True,'budgetTokens':250000,'globalRevision':7}
            from PIL import Image
            pixels=io.BytesIO();Image.new('RGB',(1,1)).save(pixels,format='PNG')
            model.media_resolver=lambda ref: ({'type':'image','mediaType':'image/png','data':base64.b64encode(pixels.getvalue()).decode()}
                if ref=='own-image' else {'type':'text','text':'Own extracted document'})
            rid,op=self.operation('summary');self.operations.observe(model,rid)
            messages=[{'role':'user','content':[{'type':'text','text':'Own input 雪 "quoted"'},
                {'type':'text','text':'uint64: 18446744073709551615'},
                {'type':'image','reference':'own-image'},{'type':'document','reference':'own-document'}]}]
            result=await model.response(messages,'Own system instructions',[{'name':'own_tool','description':'Own schema',
                'inputSchema':{'type':'object','properties':{'value':{'type':'integer'}}}}],'none')
            self.operations.finish(rid,result=result,attempted=True)
            self.assertEqual(body(self.store,self.sid,rid),received[-1])
            row=self.store.db.execute('SELECT sha256,metadata FROM studio_requests WHERE request_id=?',(rid,)).fetchone()
            meta=json.loads(row['metadata']);self.assertEqual(row['sha256'],hashlib.sha256(received[-1]).hexdigest())
            self.assertEqual(meta['purpose'],'summary');self.assertEqual(meta['httpStatus'],200)
            self.assertTrue(meta['dispatchAt'] and meta['responseAt']);self.assertTrue(model.closed_confirmed)
        self.assertEqual(len(received),3)

    async def test_dedup_retention_preserves_hash_identity_and_counter(self):
        first,raw=self.capture();second,_=self.capture(raw.decode())
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_request_bodies').fetchone()[0],1)
        with self.store.db:used=total(self.store.db,self.sid,'requests')
        self.assertEqual(used,self.store.db.execute('SELECT SUM(length(compressed)) FROM studio_request_bodies').fetchone()[0])
        with self.store.db:self.store.db.execute("UPDATE studio_model_calls SET phase='completed'")
        replacement='{"model":"own-model","input":"Different request with enough content"}'
        ceiling=max(used,len(zlib.compress(replacement.encode(),3)))+1
        with patch('request_capture.BODY_BUDGET',ceiling):third,_=self.capture(replacement)
        for rid in (first,second):
            with self.assertRaises(ProjectFault) as caught:body(self.store,self.sid,rid)
            self.assertEqual(caught.exception.code,410)
        self.assertIn(b'Different',body(self.store,self.sid,third))
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_requests').fetchone()[0],3)

    async def test_capture_failure_prevents_dispatch_and_prepared_is_not_received(self):
        model=ModelTransport({'kind':'local','baseUrl':'http://127.0.0.1:1/v1','auth':'none','protocol':'responses'},'own-model')
        rid,_=self.operation();self.operations.observe(model,rid)
        with patch('request_capture.BODY_BUDGET',1):
            with self.assertRaises(ProjectFault):await model.response([{'role':'user','content':[{'type':'text','text':'Own'}]}],'',[])
        self.assertIsNone(model.child);self.assertFalse(model.attempted)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_requests').fetchone()[0],0)
        rid,_=self.capture();meta=json.loads(self.store.db.execute('SELECT metadata FROM studio_requests WHERE request_id=?',(rid,)).fetchone()[0])
        self.assertIsNone(meta['dispatchAt']);self.assertIsNone(meta['responseAt'])

    async def test_scope_corruption_and_actual_session_deletion_selection(self):
        rid,raw=self.capture()
        foreign=str(uuid.uuid4())
        with self.assertRaises(ProjectFault):body(self.store,foreign,rid)
        self.store.db.execute('UPDATE studio_request_bodies SET compressed=?',(b'corrupt',));self.store.db.commit()
        with self.assertRaises(ProjectFault) as caught:body(self.store,self.sid,rid)
        self.assertEqual(caught.exception.code,503)
        selected=list(selections(self.store.db,self.sid))
        with self.store.db:
            self.store.db.execute('PRAGMA defer_foreign_keys=ON')
            selected.sort(key=lambda v:v[0] in ('runs','sessions'))
            for table,where,args in selected:self.store.db.execute('DELETE FROM "'+table+'" WHERE '+where,args)
        self.assertFalse(self.store.db.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_request_bodies').fetchone()[0],0)

    async def test_pending_original_is_not_expired_by_another_capture(self):
        rid,raw=self.capture()
        with self.store.db:used=total(self.store.db,self.sid,'requests')
        with patch('request_capture.BODY_BUDGET',used+5):
            with self.assertRaises(ProjectFault):self.capture('{"model":"own-model","input":"Different original"}')
        self.assertEqual(body(self.store,self.sid,rid),raw)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_requests').fetchone()[0],1)

    async def test_metadata_retention_and_read_no_initialization(self):
        self.assertFalse(exists(self.store.db))
        with self.assertRaises(ProjectFault):body(self.store,self.sid,str(uuid.uuid4()))
        self.assertFalse(exists(self.store.db))
        with patch('request_capture.MAX_REQUESTS',2):
            for i in range(4):
                rid,_=self.capture(json.dumps({'model':'own-model','input':str(i)}))
                with self.store.db:self.store.db.execute("UPDATE studio_model_calls SET phase='completed' WHERE request_id=?",(rid,))
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_requests').fetchone()[0],2)
        self.assertEqual(self.store.db.execute('SELECT dropped FROM studio_request_retention').fetchone()[0],2)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_request_bodies').fetchone()[0],2)
