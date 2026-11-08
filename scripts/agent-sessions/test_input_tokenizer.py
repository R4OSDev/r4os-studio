"""Offline tokenizer oracles, unsupported mappings and bound cache behavior."""
import unittest
from unittest.mock import patch

from input_budget import estimate
from input_count import PROFILE as CHARACTERS
from input_tokenizer import PROFILE,manifest,library,encoding,cached_count,count
from model_transport import dumps


def binding(model='gpt-4o'):
    return {'id':'own-provider','kind':'openai-compatible','baseUrl':'https://api.openai.com/v1',
        'protocol':'responses','model':model,'revision':1,'credentialRevision':2}


class InputTokenizer(unittest.TestCase):
    def setUp(self):
        cached_count.cache_clear();encoding.cache_clear();library.cache_clear();manifest.cache_clear()

    def test_reference_text_counts_offline_and_disjoint_full_body(self):
        samples=['hello world','Grüße aus Köln.','你好世界','e\u0301 👩‍💻','<|endoftext|>',
            '{"type":"object","properties":{"path":{"type":"string"}}}']
        # Independently obtained from the unmodified upstream 0.14.0 wheel.
        expected={'o200k_base':[2,6,2,7,7,14],'cl100k_base':[2,7,5,8,7,14]}
        with patch('urllib.request.urlopen',side_effect=AssertionError('No runtime downloads')):
            for name,values in expected.items():
                self.assertEqual([count(name,binding(),text) for text in samples],values)
            raw=dumps({'model':'gpt-4o','instructions':'Own system instructions','tools':[],
                'input':[{'role':'user','content':'Own Unicode input ä 雪'}]})
            result=estimate(raw,{'schema':4,'counting':PROFILE},binding())
            self.assertEqual(result['source'],'local-tokenizer');self.assertEqual(result['tokenizer']['encoding'],'o200k_base')
            self.assertEqual(result['accuracy'],'estimated')
            self.assertEqual(sum(v['tokens'] for v in result['categories']),result['tokens'])
            self.assertEqual(sum(v['bytes'] for v in result['categories']),len(raw.encode()))

    def test_unknown_model_connection_and_unavailable_assets_use_visible_fallback(self):
        raw=dumps({'input':'Own preserved text ä'})
        policies={'schema':4,'counting':PROFILE};baseline=estimate(raw,{'schema':4,'counting':CHARACTERS},binding())
        for facts in (binding('gpt-6.1-sol'),{**binding(),'baseUrl':'https://custom.example/v1'},
                {**binding(),'kind':'claude-plan'}):
            value=estimate(raw,policies,facts)
            self.assertEqual(value['tokens'],baseline['tokens']);self.assertEqual(value['source'],'character-estimate')
            self.assertTrue(value['fallbackReason']);self.assertIsNone(value['tokenizer'])
        with patch('input_tokenizer.platform.machine',return_value='unsupported'):
            value=estimate(raw,policies,binding())
        self.assertEqual(value['tokens'],baseline['tokens']);self.assertEqual(value['source'],'character-estimate')

    def test_cache_binding_invalidation_and_bounded_large_text(self):
        text='Own stable tool description'
        count('o200k_base',binding(),text);first=cached_count.cache_info()
        count('o200k_base',binding(),text);self.assertEqual(cached_count.cache_info().hits,first.hits+1)
        for facts in ({**binding(),'revision':2},{**binding(),'credentialRevision':3},binding('gpt-5')):
            count('o200k_base',facts,text)
        self.assertEqual(cached_count.cache_info().misses,first.misses+3)
        before=cached_count.cache_info();count('o200k_base',binding(),'Large text '*40000)
        self.assertEqual(cached_count.cache_info(),before)
        self.assertLessEqual(cached_count.cache_info().currsize,32)


if __name__=='__main__':unittest.main()
