"""Count-only HTTP, frozen consent, failures, cancellation and cache binding."""
import asyncio
import json
import hashlib
import unittest
from unittest.mock import AsyncMock,patch

from input_count import PROFILE
from model_transport import ModelTransport,ModelFault,dumps
from provider_count import CONTRACT,supported


class ProviderCount(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.received=[];self.events=[];self.status=200;self.tokens=321;self.delay=False
        self.arrived=asyncio.Event();self.release=asyncio.Event()
        self.server=await asyncio.start_server(self.handle,'127.0.0.1',0)
        self.addAsyncCleanup(self.stop)
        self.port=self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.release.set();self.server.close();await self.server.wait_closed()

    async def handle(self,reader,writer):
        try:
            header=(await reader.readuntil(b'\r\n\r\n')).decode()
            length=int(next(line.split(':',1)[1] for line in header.splitlines() if line.lower().startswith('content-length:')))
            raw=await reader.readexactly(length);self.received.append((header.splitlines()[0],raw));self.arrived.set()
            if self.delay:await self.release.wait()
            body=dumps({'object':'response.input_tokens','input_tokens':self.tokens} if self.status==200 else {'error':{'code':'own_count_error'}}).encode()
            writer.write(f'HTTP/1.1 {self.status} Own\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)
            await writer.drain()
        except (OSError,asyncio.IncompleteReadError):pass
        finally:writer.close();await writer.wait_closed()

    def model(self,enabled=True):
        model=ModelTransport({'id':'own-provider','kind':'local','baseUrl':f'http://127.0.0.1:{self.port}/v1',
            'protocol':'responses','auth':'none','revision':1,'credentialRevision':0,'contextWindow':1000000,
            'inputTokenCounting':True,'reasoning':'unsupported'},'own-model')
        model.context_policy={'schema':4,'counting':PROFILE.copy(),'enabled':True,'budgetTokens':2000,
            'providerCount':{'version':1,'enabled':enabled,'contract':CONTRACT}}
        model.count_observer=lambda record:self.events.append(record)
        self.addAsyncCleanup(model.close)
        return model

    def body(self,model,text='Own required input. '*1000):
        return model.freeze([{'role':'user','content':[{'type':'text','text':text}]}],
            'Own system',[],'none')[0]

    async def test_count_only_real_node_http_coalesces_and_precedes_local_rejection(self):
        model=self.model();body=self.body(model)
        self.assertGreater(model.input_estimate(body)['tokens'],2000)
        # Only this isolated loopback fixture substitutes the capability. The
        # production qualifier below never accepts this local connection.
        self.assertFalse(supported(model.binding))
        with patch('provider_count.supported',return_value=True):
            await asyncio.gather(model.count_input(body),model.count_input(body))
            await model.count_input(body)
        self.assertEqual(len(self.received),1);self.assertEqual(self.received[0][0],'POST /v1/responses/input_tokens HTTP/1.1')
        sent=json.loads(self.received[0][1]);self.assertEqual(sent['input'],body['input'])
        self.assertNotIn('stream',sent);self.assertNotIn('store',sent)
        model.check_input(body)
        count=model.input_estimate(body)['providerCount']
        self.assertEqual(count['inputTokens'],321);self.assertEqual(count['purpose'],'input-count')
        self.assertTrue(count['closedConfirmed']);self.assertTrue(count['processEnd']['confirmed'])
        self.assertEqual(count['countBodySha256'],hashlib.sha256(self.received[0][1]).hexdigest())
        self.assertEqual([event['state'] for event in self.events],['checking','complete'])
        self.assertFalse(model.attempted)
        from types import SimpleNamespace
        from studio_context import StudioContext
        messages=[{'role':'user','content':[{'type':'text','text':'Own required input. '*1000}]}]
        context=StudioContext.__new__(StudioContext)
        context.w=SimpleNamespace(config={'contextPolicy':model.context_policy,'effort':'none'},
            transport=lambda:model,history_reader=SimpleNamespace(cacheable=True))
        context.history=lambda:(messages,messages,None)
        context.report=lambda instructions,tools:(messages,messages,None,None,1000000,*context.estimate(messages,instructions,tools))
        with patch('provider_count.supported',return_value=True):
            active,progress=await context.compact('Own system',[])
        self.assertEqual(active,messages);self.assertFalse(progress);self.assertEqual(len(self.received),1)
        model.credential='changed-own-credential'
        with self.assertRaises(ModelFault):model.check_input(body)

    async def test_disabled_and_unverified_connections_do_not_count(self):
        for enabled in (False,True):
            model=self.model(enabled);body=self.body(model)
            with patch('provider_count.request',new=AsyncMock()) as request:
                await model.count_input(body);request.assert_not_awaited()
        self.assertEqual(self.received,[])
        official={'kind':'openai-compatible','baseUrl':'https://api.openai.com/v1','protocol':'responses','auth':'bearer'}
        self.assertTrue(supported(official))
        self.assertFalse(supported({**official,'kind':'codex-subscription','baseUrl':'https://chatgpt.com/backend-api/codex'}))
        self.assertFalse(supported({**official,'protocol':'chat-completions'}))

    async def test_provider_overflow_payload_change_errors_and_backoff(self):
        model=self.model();body=self.body(model,'Short current input')
        self.tokens=3000
        with patch('provider_count.supported',return_value=True):await model.count_input(body)
        with self.assertRaises(ModelFault):model.check_input(body)
        other=self.body(model,'Different short current input')
        self.assertNotIn('admissionTokens',model.input_estimate(other))
        self.status=429
        with patch('provider_count.supported',return_value=True):
            await model.count_input(other)
            third=self.body(model,'Third current input');await model.count_input(third)
        self.assertEqual(len(self.received),2)
        self.assertEqual(self.events[-1]['state'],'unavailable')
        model.check_input(third)  # Local fallback fits; no retry/inference.
        self.assertFalse(model.attempted)

    async def test_cancel_closes_original_counter_and_records_interruption(self):
        model=self.model();body=self.body(model);self.delay=True
        with patch('provider_count.supported',return_value=True):
            task=asyncio.create_task(model.count_input(body));await asyncio.wait_for(self.arrived.wait(),3)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(self.events[-1]['state'],'interrupted')
        self.assertTrue(self.events[-1]['closedConfirmed']);self.assertTrue(self.events[-1]['processEnd']['confirmed'])
        self.assertFalse(model.attempted)

    async def test_invalid_count_is_not_zero_and_credential_revision_rechecks(self):
        model=self.model();body=self.body(model);self.tokens=True
        with patch('provider_count.supported',return_value=True):await model.count_input(body)
        self.assertEqual(self.events[-1]['state'],'unavailable')
        self.assertNotIn('admissionTokens',model.input_estimate(body))
        model.binding['credentialRevision']=1;self.tokens=500
        with patch('provider_count.supported',return_value=True):await model.count_input(body)
        self.assertEqual(len(self.received),2);self.assertEqual(model.input_estimate(body)['admissionTokens'],500)


if __name__=='__main__':unittest.main()
