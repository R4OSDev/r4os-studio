"""Full input admission with Unicode, frozen old contracts and no inferred usage."""
import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

from input_budget import estimate
from input_count import PROFILE
from model_transport import ModelFault,dumps
import test_input_budget as fixtures


def policy(budget=250000):
    return {'schema':4,'counting':PROFILE.copy(),'enabled':True,'budgetTokens':budget}


class InputCount(unittest.IsolatedAsyncioTestCase):
    async def test_full_request_all_protocols_and_real_overflow_before_dispatch(self):
        messages=[{'role':'user','content':[{'type':'text','text':'Create the requested app.'}]}]
        tools=[{'name':'own_tool','description':'Own schema description. '*4000,'inputSchema':{'type':'object','properties':{}}}]
        instructions='Own system instructions. '*2500
        for protocol in ('responses','chat-completions','messages'):
            with self.subTest(protocol=protocol):
                model=fixtures.transport(protocol);model.context_policy=policy(100000)
                body,_=model.freeze(messages,instructions,tools,'none');raw=model.encoded(body)
                legacy=estimate(raw);new=model.input_estimate(body)
                self.assertGreater(legacy['tokens'],100000)
                self.assertLess(new['tokens'],100000);model.check_input(body)
                self.assertEqual(new['characters'],len(raw))
                self.assertEqual(sum(v['bytes'] for v in new['categories']),len(raw.encode()))
                self.assertEqual(sum(v['tokens'] for v in new['categories']),new['tokens'])
                self.assertEqual(model.encoded(body),raw)
                self.assertEqual(new['accuracy'],'estimated')
                huge=[{'role':'user','content':[{'type':'text','text':'Current unremovable input. '*20000}]}]
                with patch('model_transport.resolve_binding',new=AsyncMock()) as dns:
                    with self.assertRaises(ModelFault) as caught:await model.response(huge,instructions,tools,'none')
                    self.assertEqual(caught.exception.code,'context_input_limit');dns.assert_not_awaited()

    async def test_unicode_rasters_and_same_count_used_in_breakdown(self):
        from PIL import Image
        from request_breakdown import analyze
        stream=io.BytesIO();Image.new('RGB',(1,1)).save(stream,format='PNG')
        data=base64.b64encode(stream.getvalue()).decode()
        raw=dumps({'instructions':'ä 中文 e\u0301 👩‍💻','input':[{'role':'user','content':[
            {'type':'input_text','text':'Own input'},{'type':'input_image','image_url':'data:image/png;base64,'+data}]}]})
        value=estimate(raw,policy(),{'model':'own-model'})
        self.assertLess(value['characters'],value['bytes']);self.assertEqual(value['mediaTokens'],65536)
        self.assertEqual(value['characters']-value['textCharacters'],len(data))
        measured=analyze(raw,{'contextWindow':1000000},policy(),value)
        self.assertEqual(measured['estimatedInput'],value['tokens']);self.assertEqual(measured['categories'],value['categories'])
        with self.assertRaises(ModelFault):estimate('{"input":[{"type":"input_image","image_url":"https://invalid.test/image.png"}]}',policy(),{})

    async def test_irreducible_first_input_reports_required_parts(self):
        from studio_context import StudioContext
        config={'contextPolicy':policy(1000),'apiProvider':{'protocol':'responses'}}
        value=estimate(dumps({'instructions':'Required system '*1000,'input':'Current user'}),config['contextPolicy'],{})
        messages=[{'sequence':1,'role':'user','content':[{'type':'text','text':'Current user'}]}]
        context=StudioContext.__new__(StudioContext);context.w=SimpleNamespace(config=config)
        context.input_count=value
        context.report=lambda *a,**k:(messages,messages,None,None,100000,value['tokens'],value['bytes'])
        with self.assertRaises(ModelFault) as caught:await context.compact('Required system',[])
        self.assertEqual(caught.exception.code,'context_required_input_limit')
        self.assertEqual(caught.exception.details['system'],next(x['tokens'] for x in value['categories'] if x['id']=='system'))
        self.assertNotIn('unresolved tool observations',str(caught.exception))

    async def test_original_policy_and_model_limits_cannot_be_reinterpreted(self):
        model=fixtures.transport();messages=[{'role':'user','content':[{'type':'text','text':'Original ä'}]}]
        body,_=model.freeze(messages,'Original instructions',[],'none');raw=model.encoded(body)
        old=model.input_estimate(body)
        self.assertEqual(old,estimate(raw));self.assertNotIn('characters',old)
        model.context_policy=policy();new=model.input_estimate(body)
        self.assertLess(new['tokens'],old['tokens'])
        model.binding.update(contextWindow=1000,maxOutputTokens=900)
        with self.assertRaises(ModelFault):model.check_input(body)
        model.context_policy={'schema':3,'enabled':True,'budgetTokens':250000}
        self.assertEqual(model.input_estimate(body),old)


if __name__=='__main__':unittest.main()
