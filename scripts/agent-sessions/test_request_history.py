"""Accounting provenance, historical limits, indexed paging and raw byte reads."""
import base64
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock

from request_breakdown import analyze
from request_capture import transport
from request_history import page,detail,chunk
from session_store import encode
from store import ProjectFault
import test_request_capture as fixtures


class RequestHistory(fixtures.CaptureFixture,unittest.TestCase):
    def sent(self,raw=None):
        rid,_=self.capture() if raw is None else self.capture(raw)
        transport(self.store,rid,'dispatch');return rid

    def test_first_required_input_is_archived_without_model_call_or_false_measurement(self):
        import asyncio
        from input_count import PROFILE
        from model_transport import ModelTransport,ModelFault
        from studio_context import StudioContext
        from session_context import saved
        model=ModelTransport({'id':self.fixture.provider,'kind':'local','protocol':'responses','reasoning':'unsupported',
            'contextWindow':1000000,'baseUrl':'http://127.0.0.1:1/v1','auth':'none'},'own-model')
        model.context_policy={'schema':4,'counting':PROFILE.copy(),'enabled':True,'budgetTokens':1000}
        config={'contextPolicy':model.context_policy,'effort':'none','providerId':self.fixture.provider}
        context=StudioContext.__new__(StudioContext)
        context.w=SimpleNamespace(config=config,store=self.store,session_id=self.sid,run_id=self.run['id'],
            transport=lambda:model,prepared_transport=model,history_reader=SimpleNamespace(cacheable=True))
        messages=[{'sequence':1,'role':'user','content':[{'type':'text','text':'Own first input'}]}]
        context.history=lambda:(messages,messages,None)
        context.report=lambda instructions,tools:(messages,messages,None,None,1000000,*context.estimate(messages,instructions,tools))
        with self.assertRaises(ModelFault) as caught:asyncio.run(context.prepare('Required system '*2000,[]))
        context.failed(caught.exception)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_model_calls').fetchone()[0],0)
        self.assertEqual(page(self.store,self.sid)['requests'],[])
        self.assertTrue(page(self.store,self.sid)['blockedAvailable'])
        item=page(self.store,self.sid,kind='blocked')['requests'][0]
        self.assertEqual(item['status'],'blocked-before-send')
        value=detail(self.store,self.sid,item['id'])
        self.assertIsNone(value['usage']['input']);self.assertIn('system',value['blockedReason'])
        raw=base64.b64decode(chunk(self.store,self.sid,item['id'])['base64']).decode()
        self.assertEqual(json.loads(raw)['instructions'],'Required system '*2000)
        snapshot=saved(self.store,self.sid)
        self.assertEqual(snapshot['state'],'blocked');self.assertEqual(snapshot['blockedRequestId'],item['id'])
        self.assertNotIn('earlier context',snapshot['reason'])

    def test_blocked_history_is_separate_exact_bounded_and_read_only(self):
        from input_count import PROFILE
        from request_capture import capture
        from model_transport import ModelFault
        op={'runId':self.run['id'],'sessionId':self.sid,'owner':{'type':self.store.owner_type,'id':self.store.owner_id},
            'selection':{'providerId':self.fixture.provider},'purpose':'conversation'}
        raw='{ "model":"own-model", "input":"'+('雪'*30000)+'", "n":18446744073709551615 }'
        ids=[]
        with patch('request_capture.MAX_REQUESTS',2):
            for _ in range(3):
                rid=str(uuid.uuid4());ids.append(rid)
                capture(self.store,{**op,'requestId':rid},raw,{'model':'own-model','protocol':'responses','contextWindow':1000000},
                    {'schema':4,'counting':PROFILE.copy(),'enabled':True,'budgetTokens':1000},blocked=ModelFault('context_input_limit',not_dispatched=True))
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM studio_requests').fetchone()[0],2)
        changes=self.store.db.total_changes
        latest=page(self.store,self.sid,count=1,kind='blocked')
        self.assertEqual(latest['requests'][0]['id'],ids[-1])
        self.assertEqual(page(self.store,self.sid,latest['nextBefore'],1,'blocked')['requests'][0]['id'],ids[-2])
        self.assertEqual(detail(self.store,self.sid,ids[-1])['older'],ids[-2])
        blocks=[];offset=0
        while True:
            value=chunk(self.store,self.sid,ids[-1],offset);blocks.append(base64.b64decode(value['base64']))
            if value['nextOffset'] is None:break
            offset=value['nextOffset']
        self.assertEqual(b''.join(blocks),raw.encode())
        self.assertEqual(self.store.db.total_changes,changes)
        sent=self.sent();self.assertEqual(page(self.store,self.sid)['requests'][0]['id'],sent)
        self.assertIsNone(detail(self.store,self.sid,sent)['older'])
        self.assertEqual(detail(self.store,self.sid,ids[-1])['total'],2)

    def test_final_input_rejection_records_prepared_bytes_before_any_dns(self):
        import asyncio
        from input_count import PROFILE
        from model_transport import ModelTransport,ModelFault
        model=ModelTransport({'id':self.fixture.provider,'kind':'local','protocol':'responses','reasoning':'unsupported',
            'contextWindow':1000000,'baseUrl':'http://127.0.0.1:1/v1','auth':'none'},'own-model')
        model.context_policy={'schema':4,'counting':PROFILE.copy(),'enabled':True,'budgetTokens':1}
        rid,_=self.operation();self.operations.observe(model,rid)
        with patch('model_transport.resolve_binding',new=AsyncMock()) as dns:
            with self.assertRaises(ModelFault) as caught:asyncio.run(model.response([{'role':'user','content':[{'type':'text','text':'Own final input'}]}],'Own system',[],'none'))
            dns.assert_not_awaited()
        self.operations.finish(rid,error=caught.exception,attempted=False)
        self.assertFalse(model.attempted)
        self.assertEqual(page(self.store,self.sid)['requests'],[])
        self.assertEqual(detail(self.store,self.sid,rid)['status'],'blocked-before-send')

    def test_disjoint_original_spans_all_protocols_cache_and_media(self):
        for body in [
            {'instructions':'Own system 雪','tools':[{'name':'own','parameters':{'type':'object'}}],'input':[{'role':'developer','content':'Own prefix'},{'role':'user','content':'Own input'},{'type':'function_call_output','output':'Own tool result'}],'model':'own'},
            {'system':[{'text':'Own system','cache_control':{'type':'ephemeral'}}],'tools':[],'messages':[{'role':'user','content':[{'type':'text','text':'Own document'}]}],'model':'own'},
            {'messages':[{'role':'system','content':'Own system'},{'role':'developer','content':'Own workspace'},{'role':'tool','content':'Own result'}],'tools':[],'model':'own'}]:
            raw=json.dumps(body,ensure_ascii=True,indent=2)
            result=analyze(raw,{'contextWindow':1000000},{'schema':3,'enabled':True,'budgetTokens':50000})
            self.assertEqual(result['state'],'estimated')
            self.assertEqual(sum(v['tokens'] for v in result['categories']),result['estimatedInput'])
            self.assertEqual(sum(v['bytes'] for v in result['categories']),len(raw.encode()))
            self.assertEqual(result['free'],50000-result['estimatedInput'])
            self.assertEqual(result['outputReserve'],200000)
        unknown=analyze('{"input":[{"type":"input_image","image_url":"https://unavailable.invalid/pixels"}]}',{},None)
        self.assertEqual(unknown['state'],'unavailable');self.assertIsNone(unknown['free'])

    def test_immutable_policy_limits_usage_and_no_cache_double_count(self):
        rid=self.sent();transport(self.store,rid,'response',200)
        operation=self.operations.row(rid)[1]
        operation['usage']={'input_tokens':10,'cache_read_input_tokens':20,'cache_creation_input_tokens':30,'output_tokens':900}
        with self.store.db:
            self.store.db.execute("UPDATE studio_model_calls SET phase='completed',data=? WHERE request_id=?",(encode(operation),rid))
            self.store.db.execute('UPDATE studio_requests SET metadata=json_remove(metadata,\'$.context\') WHERE request_id=?',(rid,))
            # Stored protocol is from the actual body; make this a Messages fixture.
            self.store.db.execute("UPDATE studio_requests SET metadata=json_set(metadata,'$.protocol','messages') WHERE request_id=?",(rid,))
            settings=json.loads(self.store.row(self.sid)['settings']);settings['contextLimit']={'mode':'on','budgetTokens':1}
            self.store.db.execute('UPDATE sessions SET settings=? WHERE id=?',(encode(settings),self.sid))
        result=detail(self.store,self.sid,rid)
        self.assertEqual(result['context']['inputLimit'],250000)
        self.assertEqual(result['policy']['globalRevision'],7)
        self.assertEqual(result['usage']['input'],60);self.assertEqual(result['usage']['cachedInput'],20)
        self.assertEqual(result['usage']['source'],'provider-response')
        overflow=analyze('{"input":"Own context"}',{'contextWindow':10000,'maxOutputTokens':4000},{'schema':3,'enabled':True,'budgetTokens':1000})
        self.assertEqual(overflow['capacity'],1000);self.assertEqual(overflow['free'],0);self.assertGreater(overflow['overflow'],0)

    def test_cursor_neighbors_live_addition_and_prepared_exclusion(self):
        self.capture();ids=[self.sent() for _ in range(4)]
        first=page(self.store,self.sid,count=2);self.assertEqual([v['id'] for v in first['requests']],list(reversed(ids[2:])))
        second=page(self.store,self.sid,first['nextBefore'],2);self.assertEqual([v['id'] for v in second['requests']],list(reversed(ids[:2])))
        self.assertIsNone(second['nextBefore'])
        selected=detail(self.store,self.sid,ids[1]);self.assertEqual(selected['older'],ids[0]);self.assertEqual(selected['newer'],ids[2])
        self.sent();again=detail(self.store,self.sid,ids[1]);self.assertEqual(again['id'],selected['id']);self.assertEqual(again['position'],2)
        self.assertEqual(again['total'],5)
        query=self.store.db.execute('EXPLAIN QUERY PLAN SELECT request_id FROM studio_requests WHERE session_id=? AND dispatch_at IS NOT NULL AND (dispatch_at,seq)<(?,?) ORDER BY dispatch_at DESC,seq DESC LIMIT 20',(self.sid,'9999',9999)).fetchall()
        self.assertTrue(any('studio_requests_dispatch' in str(tuple(r)) for r in query))

    def test_history_orders_by_observed_dispatch_not_prepare_order(self):
        first,_=self.capture();second,_=self.capture()
        transport(self.store,second,'dispatch');transport(self.store,first,'dispatch')
        newest=page(self.store,self.sid,count=1)
        self.assertEqual(newest['requests'][0]['id'],first)
        earlier=page(self.store,self.sid,before=newest['nextBefore'],count=1)
        self.assertEqual(earlier['requests'][0]['id'],second)
        self.assertEqual(detail(self.store,self.sid,first)['older'],second)
        self.assertEqual(detail(self.store,self.sid,second)['newer'],first)
        self.assertEqual(detail(self.store,self.sid,first)['position'],2)

    def test_body_chunk_exact_unicode_uint64_scope_and_no_original_writes(self):
        raw='{ "model":"own-model", "input":"'+('雪\\n"quoted"'.replace('"','\\"')*10000)+'", "n":18446744073709551615 }'
        json.loads(raw);rid=self.sent(raw)
        changes=self.store.db.total_changes;blocks=[];offset=0
        while True:
            result=chunk(self.store,self.sid,rid,offset,65536);blocks.append(base64.b64decode(result['base64']))
            if result['nextOffset'] is None:break
            offset=result['nextOffset']
        self.assertEqual(b''.join(blocks),raw.encode());self.assertEqual(self.store.db.total_changes,changes)
        with self.assertRaises(ProjectFault):chunk(self.store,str(uuid.uuid4()),rid)
        with self.assertRaises(ProjectFault):detail(self.store,self.sid,str(uuid.uuid4()))
        with self.assertRaises(ProjectFault):chunk(self.store,self.sid,rid,-1)
        with self.assertRaises(ProjectFault):chunk(self.store,self.sid,rid,len(raw.encode())+1)

    def test_empty_and_native_no_schema_creation_and_owner_guard(self):
        changes=self.store.db.total_changes;self.assertEqual(page(self.store,self.sid)['requests'],[])
        self.assertEqual(self.store.db.total_changes,changes)
        rid=self.sent()
        with self.store.db:self.store.db.execute("UPDATE studio_requests SET metadata=json_set(metadata,'$.owner.id',?) WHERE request_id=?",(str(uuid.uuid4()),rid))
        with self.assertRaises(ProjectFault):detail(self.store,self.sid,rid)
