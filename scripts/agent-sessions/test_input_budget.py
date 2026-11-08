"""Full request boundaries, lower model ceilings and no dispatch on rejection."""
import base64
import io
import unittest
from unittest.mock import AsyncMock,patch

from input_budget import estimate,limit
from model_transport import ModelFault,ModelTransport,dumps


def transport(protocol='responses',budget=10000):
    model=ModelTransport({'id':'own-provider','kind':'local','server':'custom','baseUrl':'http://127.0.0.1:1/v1',
        'protocol':protocol,'auth':'none','reasoning':'unsupported','contextWindow':1000000,'maxOutputTokens':1000},
        'own-model',chat_policy={'reasoning':'none'})
    model.context_policy={'schema':3,'enabled':True,'budgetTokens':budget}
    return model


class InputBudget(unittest.IsolatedAsyncioTestCase):
    async def test_all_protocols_check_large_instructions_tools_and_documents_before_dns(self):
        for protocol in ('responses','messages','chat-completions'):
            for source in ('instructions','tools','document'):
                with self.subTest(protocol=protocol,source=source):
                    model=transport(protocol)
                    messages=[{'role':'user','content':[{'type':'text','text':'Short current input'}]}]
                    instructions='Large system/workspace instructions. '*500 if source=='instructions' else 'Own instructions'
                    tools=[{'name':'own_tool','description':'Large tool schema. '*1000,'inputSchema':{'type':'object','properties':{}}}] if source=='tools' else []
                    if source=='document':
                        messages[0]['content'].append({'type':'document','reference':'own-document'})
                        model.media_resolver=lambda _: {'type':'text','text':'Extracted document content. '*1000}
                    with patch('model_transport.resolve_binding',new=AsyncMock()) as dns,patch('asyncio.create_subprocess_exec',new=AsyncMock()) as process:
                        with self.assertRaises(ModelFault) as caught:await model.response(messages,instructions,tools,'none')
                    self.assertEqual(caught.exception.code,'context_input_limit')
                    self.assertEqual(caught.exception.category,'context');self.assertTrue(caught.exception.not_dispatched)
                    self.assertFalse(model.attempted);dns.assert_not_awaited();process.assert_not_awaited()

    async def test_exact_local_boundary_cached_input_and_lower_model_output_reservation(self):
        model=transport();messages=[{'role':'user','content':[{'type':'text','text':'Own repeated input'}]}]
        body,_=model.freeze(messages,'Own instructions',[],'none')
        value=model.input_estimate(body);self.assertGreater(value['tokens'],value['textBytes'])
        model.context_policy['budgetTokens']=value['tokens'];model.check_input(body)
        model.context_policy['budgetTokens']-=1
        with self.assertRaises(ModelFault):model.check_input(body)
        # Cache controls never discount prompt content; signed blocks and
        # historical tool schemas remain charged as part of the full body.
        self.assertGreater(estimate(dumps({'system':[{'text':'x'*10000,'cache_control':{'type':'ephemeral'}}]}))['tokens'],10000)
        self.assertEqual(limit({'enabled':True,'budgetTokens':500000},{'contextWindow':10000,'maxOutputTokens':4000}),6000)
        self.assertEqual(limit({'enabled':False,'budgetTokens':1},{'contextWindow':10000,'maxOutputTokens':4000}),6000)
        self.assertEqual(limit({'enabled':True,'budgetTokens':500},{'contextWindow':10000,'maxOutputTokens':4000}),500)
        self.assertEqual(limit({'enabled':False},{'protocol':'messages','contextWindow':10000}),1808)
        model.context_policy={'schema':3,'enabled':False,'budgetTokens':1}
        model.binding['contextWindow']=1000;model.binding['maxOutputTokens']=900
        with self.assertRaises(ModelFault):model.check_input(body)
        model.binding['contextWindow']=1000000;model.check_input(body)

    async def test_compressed_raster_is_not_free_and_unknown_media_is_not_sent(self):
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(1,1)).save(stream,format='PNG');data=base64.b64encode(stream.getvalue()).decode()
        for protocol in ('responses','messages','chat-completions'):
            with self.subTest(protocol=protocol):
                model=transport(protocol,50000);model.media_resolver=lambda _: {'type':'image','mediaType':'image/png','data':data}
                messages=[{'role':'user','content':[{'type':'image','reference':'own-pixels'}]}]
                body,_=model.freeze(messages,'Own instructions',[],'none');value=model.input_estimate(body)
                self.assertEqual(value['mediaTokens'],65536);self.assertLess(value['bytes'],2000)
                with patch('model_transport.resolve_binding',new=AsyncMock()) as dns:
                    with self.assertRaises(ModelFault):await model.response(messages,'Own instructions',[],'none')
                    dns.assert_not_awaited()
        with self.assertRaises(ModelFault) as caught:estimate(dumps({'type':'input_image','image_url':'https://example.invalid/image.png'}))
        self.assertEqual(caught.exception.code,'context_input_unavailable')

    async def test_old_accepted_policy_keeps_its_original_contract(self):
        model=transport();model.context_policy={'budgetTokens':1}
        body,_=model.freeze([{'role':'user','content':[{'type':'text','text':'Own preserved old input'}]}],'Own instructions',[],'none')
        model.check_input(body)

    async def test_images_endpoint_obeys_the_same_input_policy(self):
        from image_transport import ImageTransport
        model=ImageTransport({'imageAction':'generate','protocol':'responses','contextWindow':1000000},'own-image-model')
        model.context_policy={'schema':3,'enabled':True,'budgetTokens':1000}
        with patch('model_transport.resolve_binding',new=AsyncMock()) as dns:
            with self.assertRaises(ModelFault) as caught:await model.response({'model':'own-image-model','prompt':'Own bounded prompt'},'',[])
            self.assertEqual(caught.exception.code,'context_input_limit');dns.assert_not_awaited()

    async def test_vision_child_inherits_session_policy_and_keeps_its_lower_model_limit(self):
        from types import SimpleNamespace
        from vision_analysis import snapshot,VisionTransport
        policy={'schema':3,'enabled':True,'budgetTokens':90000}
        provider={'id':'own-vision','kind':'local','protocol':'responses','auth':'none','baseUrl':'http://127.0.0.1:1/v1'}
        facts={'id':'own-model','contextWindow':10000,'maxOutputTokens':4000,
            'declaredCapabilities':{'reasoning':'unsupported'},'capabilities':{'imageInput':'supported'}}
        frozen=snapshot(SimpleNamespace(config={'contextPolicy':policy},run_id='own-parent'),'own-child',
            {'revision':1,'target':{'provider':provider,'model':facts,'effort':'none','catalogRevision':1}})
        self.assertEqual(frozen['contextPolicy'],policy);self.assertIsNot(frozen['contextPolicy'],policy)
        model=VisionTransport({**provider,**frozen['apiModel']},'own-model')
        model.context_policy=frozen['contextPolicy']
        with patch('model_transport.resolve_binding',new=AsyncMock()) as dns:
            with self.assertRaises(ModelFault) as caught:
                await model.response([{'role':'user','content':[{'type':'text','text':'Own question. '*450}]}],'Own instructions',[],'none')
            self.assertEqual(caught.exception.code,'context_input_limit');dns.assert_not_awaited()


if __name__=='__main__':unittest.main()
