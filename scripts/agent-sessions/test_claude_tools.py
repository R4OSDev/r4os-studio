"""Bound MCP transport/common receipts; no native model/account or user data."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from claude_mcp import StudioMcp,McpFault,mcp_schema
from claude_tool_broker import ClaudeToolBroker
from run_store import admit,get_run
from session_store import encode
from worker import Worker
import test_runs as fixtures


class McpTransport(unittest.TestCase):
    def test_roadmap_oneof_keeps_all_strict_object_branches(self):
        from tool_catalog import specifications
        from profile import PROFILE
        original=next(t['inputSchema'] for t in specifications(PROFILE) if t['name']=='studio_update_roadmap')
        converted=mcp_schema(original)
        self.assertEqual(converted['type'],'object')
        self.assertEqual(converted['properties']['request'],original)
        self.assertEqual(converted['required'],['request'])
        self.assertEqual(converted.get('$defs'),original.get('$defs'))
        self.assertNotIn('type',original)

    def test_native_call_metadata_and_full_result_are_preserved_with_no_extra_routes(self):
        calls=[];result={'content':[{'type':'text','text':encode({'success':True,'development':{'jobId':'owned-job'},'image':{'id':'owned-ref'}})},
            {'type':'image','mimeType':'image/png','data':'YWJj'}],'isError':False}
        def broker(value):calls.append(value);return result
        server=StudioMcp({'schema':1,'binding':{'runId':'own-run'},'tools':[{'name':'read_file','description':'Own read','inputSchema':{'type':'object'}}]},broker)
        request=lambda method,params={}:{'jsonrpc':'2.0','id':1,'method':method,'params':params}
        server.handle(request('initialize',{'protocolVersion':'2025-11-25'}))
        params={'name':'read_file','arguments':{'path':'own.c'},'_meta':{'claudecode/toolUseId':'native-id-001'}}
        self.assertEqual(server.handle(request('tools/call',params)),result)
        self.assertEqual(calls[0]['nativeToolUseId'],'native-id-001');self.assertEqual(calls[0]['binding'],{'runId':'own-run'})
        before=len(calls)
        for method,value in [('tools/call',{**params,'_meta':{}}),('tools/call',{**params,'name':'Bash'}),('resources/read',{'uri':'file:///config'}),('prompts/get',{}),('tools/list',{'cursor':'foreign'})]:
            with self.assertRaises(McpFault):server.handle(request(method,value))
        self.assertEqual(len(calls),before)


class McpBoundEffects(unittest.IsolatedAsyncioTestCase):
    async def test_original_native_tool_id_uses_common_receipts_once_and_stop_closes_admission(self):
        fixture=fixtures.Runs('test_tool_denial_and_unconfirmed_receipt_never_execute');fixture.setUp();self.addCleanup(fixture.tearDown)
        with fixture.open() as store:run,_=admit(store,fixture.sid,fixture.data,fixture.providers)
        worker=Worker({'projects':str(fixture.projects),'r4os':str(fixture.r4os),'projectId':fixture.pid,'runId':run['id']})
        self.addCleanup(worker.store.close)
        effects=[]
        async def execute(name,args,call_id):effects.append(call_id);return {'success':True,'output':'Own original result','development':{'jobId':'original-job'}}
        worker.execute=execute
        async def output(result,image_data=None):return {'content':[{'type':'text','text':encode(result)}],'isError':not result['success']}
        async def bound(name,args,call_id):return await worker.bound_tool(name,args,call_id,output)
        async def current(binding):return bool(get_run(worker.store,run['id'])['busy']) and not worker.stopping
        with tempfile.TemporaryDirectory() as root:
            broker=ClaudeToolBroker(Path(root),{'runId':run['id']},['write_file'],current,bound)
            await broker.start();self.addAsyncCleanup(broker.close)
            arguments={'path':'own.c','content':'one original effect','expectedSha256':None}
            base={'binding':broker.binding,'tool':'write_file','arguments':arguments,'nativeToolUseId':'native-original-id'}
            self.assertTrue((await broker.handle({'operation':'call',**base}))['isError']);self.assertEqual(effects,[])
            self.assertFalse(await broker.handle({'operation':'authorize',**base,'capability':'foreign'}))
            self.assertTrue(await broker.handle({'operation':'authorize',**base,'capability':broker.capability}))
            first=await broker.handle({'operation':'call',**base});second=await broker.handle({'operation':'call',**base})
            self.assertEqual(first,second);self.assertEqual(effects,['native-original-id'])
            self.assertIn('original-job',first['content'][0]['text'])
            row=worker.store.db.execute('SELECT call_id,result FROM tools').fetchone();self.assertEqual(row['call_id'],'native-original-id')
            self.assertNotIn('capability',row['result'])
            worker.stopping=True
            self.assertTrue((await broker.handle({'operation':'call',**base,'nativeToolUseId':'after-stop'}))['isError']);self.assertEqual(len(effects),1)
