"""Exercise stdio ownership, original responses and failed protocol boundaries."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from skill_mcp_client import Client, McpFault

SERVER = r'''
import json,sys,time,os
def send(v): print(json.dumps(dict(jsonrpc='2.0',**v)),flush=True)
for line in sys.stdin:
 v=json.loads(line);method=v.get('method');rid=v.get('id');params=v.get('params',{})
 if rid is None:continue
 if method=='initialize':
  send(dict(id=rid,result=dict(protocolVersion=params['protocolVersion'],capabilities={'tools':{},'resources':{},'prompts':{}},serverInfo={'name':'private-test','version':'1'})))
 elif method=='tools/list':
  if 'cursor' not in params:send(dict(id=rid,result={'tools':[{'name':'echo','inputSchema':{'type':'object','properties':{'value':{'anyOf':[{'type':'string'},{'type':'null'}]}}}}],'nextCursor':'page-two'}))
  else:send(dict(id=rid,result={'tools':[{'name':'wait','inputSchema':{'type':'object'}},{'name':'malformed','inputSchema':{'type':'object'}},{'name':'exit','inputSchema':{'type':'object'}},{'name':'large','inputSchema':{'type':'object'}}]}))
 elif method=='tools/call':
  name=params['name']
  if name=='malformed':print('not-json',flush=True);continue
  if name=='exit':sys.exit(0)
  if name=='wait':time.sleep(.15)
  if name=='large':value='evidence-'*20000
  else:value=params['arguments']
  send(dict(method='notifications/progress',params={'progressToken':params['_meta']['progressToken'],'progress':1,'total':1}))
  send(dict(id=rid,result={'content':[{'type':'text','text':json.dumps(value)},{'type':'image','data':'aW1hZ2U=','mimeType':'image/png'}],'structuredContent':{'original':value,'credentialPresent':'STUDIO_QA_SECRET' in os.environ}}))
 elif method=='ping':send(dict(id=rid,result={}))
 elif method=='resources/list':send(dict(id=rid,result={'resources':[{'uri':'private:original','name':'original evidence'}]}))
 elif method=='prompts/list':send(dict(id=rid,result={'prompts':[{'name':'native-prompt'}]}))
 else:send(dict(id=rid,error={'code':-32601,'message':'method absent'}))
'''


class Protocol(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = Client(self.root / 'MCP', dict(skill='own', run='own'))
        os.environ['STUDIO_QA_SECRET'] = 'ambient-canary-not-for-child'
        await self.client.start([sys.executable, '-u', '-c', SERVER], env={'LANG':'C.UTF-8'})
        self.tools = await self.client.discover()

    async def asyncTearDown(self):
        await self.client.close(grace=.25)
        self.assertTrue(self.client.owner['processEndConfirmed'])
        os.environ.pop('STUDIO_QA_SECRET', None)
        self.temp.cleanup()

    async def test_full_paginated_schemas_images_resources_and_exact_argument_shapes(self):
        self.assertEqual(len(self.tools), 5)
        args = dict(value=None, nested=[False, {'number':3.5}])
        result = await self.client.call('echo', args)
        self.assertEqual(result['structuredContent']['original'], args)
        self.assertFalse(result['structuredContent']['credentialPresent'])
        self.assertEqual(result['content'][1], dict(type='image', data='aW1hZ2U=', mimeType='image/png'))
        self.assertEqual(len(await self.client.listing('resources/list','resources')), 1)
        self.assertEqual(len(await self.client.listing('prompts/list','prompts')), 1)
        await self.client.request('ping',{})
        with self.assertRaises(McpFault):await self.client.call('unadvertised',{})
        with self.assertRaises(McpFault):await self.client.call('echo',[])

    async def test_timeout_keeps_the_original_and_records_late_result_without_replay(self):
        rid = str(uuid.uuid4())
        with self.assertRaises(McpFault) as failure:
            await self.client.call('wait',dict(value='once'),request_id=rid,timeout=.01)
        self.assertEqual(failure.exception.request_id,rid)
        self.assertFalse(self.client.observe(rid)['providerEndConfirmed'])
        with self.assertRaisesRegex(McpFault,'must not be submitted again'):
            await self.client.call('wait',dict(value='once'),request_id=rid)
        await asyncio.sleep(.25)
        self.assertEqual(self.client.observe(rid)['phase'],'late_result')
        result = await self.client.call('wait',dict(value='once'),request_id=rid)
        self.assertEqual(result['structuredContent']['original'],dict(value='once'))
        with self.assertRaisesRegex(McpFault,'different arguments'):
            await self.client.call('wait',dict(value='twice'),request_id=rid)
        response = self.root / 'MCP/Calls' / (rid+'.response.json')
        self.assertEqual(self.client.observe(rid)['responseBytes'],response.stat().st_size)

    async def test_large_results_are_retained_whole_and_original_ids_cannot_cross_processes(self):
        rid = str(uuid.uuid4())
        result = await self.client.call('large',{},request_id=rid)
        self.assertEqual(len(result['structuredContent']['original']),180000)
        self.assertGreater(self.client.observe(rid)['responseBytes'],320000)
        await self.client.close()
        with self.assertRaisesRegex(McpFault,'already owns'):
            await self.client.start([sys.executable,'-c',SERVER],env={})

    async def test_client_cancellation_retains_the_original_native_completion(self):
        rid=str(uuid.uuid4())
        task=asyncio.create_task(self.client.call('wait',{},request_id=rid))
        await asyncio.sleep(.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(self.client.observe(rid)['clientInterrupted'])
        self.assertFalse(self.client.observe(rid)['providerEndConfirmed'])
        await asyncio.sleep(.25)
        self.assertEqual(self.client.observe(rid)['phase'],'late_result')

    async def test_malformed_frames_keep_original_effect_unknown(self):
        rid=str(uuid.uuid4())
        with self.assertRaises(McpFault):await self.client.call('malformed',{},request_id=rid)
        self.assertEqual(self.client.observe(rid)['phase'],'unknown')
        self.assertFalse(self.client.observe(rid)['providerEndConfirmed'])

    async def test_eof_is_not_a_successful_tool_result(self):
        rid=str(uuid.uuid4())
        with self.assertRaises(McpFault):await self.client.call('exit',{},request_id=rid)
        self.assertEqual(self.client.observe(rid)['phase'],'unknown')
        self.assertFalse(self.client.observe(rid)['providerEndConfirmed'])


if __name__=='__main__':unittest.main()
