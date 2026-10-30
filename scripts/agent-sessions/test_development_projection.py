"""Bounded summaries and complete explicit original-record reads."""
import base64,copy,hashlib,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
sys.path.append(str(Path(__file__).resolve().parents[1]/'project-development'))
from contracts import DevelopmentFault
from development_projection import summary,view,encoded,LIMIT_BYTES
from development_tools import DevelopmentTools

def page():
    return {'job':{'id':'original-job','projectId':'project','kind':'build','state':'completed','phase':'published','revision':4,'exitCode':0,
        'pins':{'sdk':{'metadata':'SDK pin é🙂'*5000}},'source':{'id':'source','sha256':'a'*64},'artifactId':'artifact',
        'check':{'state':'passed','findings':['Checks passed.'],'criteria':{'stored':'criterion'*3000}}},
        'artifact':{'id':'artifact','packageSha256':'b'*64,'files':[{'path':f'Resources/{i}.dat','bytes':i,'sha256':'c'*64} for i in range(400)]},
        'output':'x'*65536,'startOffset':0,'nextOffset':65536,'pageBytes':65536,'totalBytes':119419,'hasMore':True,
        'truncated':False,'captureLimitReached':False,'captureTruncated':False}

class ProjectionTest(unittest.TestCase):
    def test_summary_identity_status_hash_and_page_capture_flags(self):
        p=page();original=copy.deepcopy(p);r=summary(p['job'],p)
        self.assertLess(len(encoded(r).encode()),LIMIT_BYTES);self.assertEqual(p,original)
        self.assertEqual(r['job']['id'],'original-job');self.assertEqual(r['job']['exitCode'],0)
        self.assertEqual(r['artifact']['packageSha256'],'b'*64);self.assertEqual(r['artifact']['fileCount'],400)
        self.assertTrue(r['outputPage']['hasMore']);self.assertEqual(r['outputPage']['totalBytes'],119419)
        self.assertFalse(r['outputPage']['truncated']);self.assertNotIn('pins',r['job']);self.assertTrue(r['presentation']['detailsOmitted'])

    def test_complete_details_inventory_hash_and_stale_foreign_cursor(self):
        p=page()
        for mode in ('details','inventory'):
            cursor=None;parts=[]
            for _ in range(300):
                r=view(p,mode,cursor);self.assertLess(len(encoded(r).encode()),LIMIT_BYTES)
                parts.append(r['fragment']);cursor=r['nextCursor']
                if not cursor:break
            raw=''.join(parts).encode();self.assertEqual(hashlib.sha256(raw).hexdigest(),r['snapshotSha256'])
            restored=json.loads(raw)
            if mode=='inventory':self.assertEqual(restored['artifact']['files'],p['artifact']['files'])
            else:self.assertEqual(restored['job']['pins'],p['job']['pins'])
            cursor=view(p,mode)['nextCursor'];self.assertIsNotNone(cursor)
            for field in ('id','revision'):
                changed=copy.deepcopy(p);changed['job'][field]='foreign' if field=='id' else 5
                with self.assertRaises(DevelopmentFault):view(changed,mode,cursor)

    def test_output_all_unicode_bytes_and_actual_capture_limit(self):
        p=page();raw=('é🙂"\\\n'*10000).encode();offset=0;found=[]
        while offset<len(raw):
            sample=raw[offset:offset+65536]
            while True:
                try:text=sample.decode();break
                except UnicodeDecodeError as error:sample=sample[:error.start]
            r=view({**p,'output':text,'totalBytes':len(raw),'captureTruncated':True},'output',offset=offset)
            found.append(r['output']['text']);self.assertLess(len(encoded(r).encode()),LIMIT_BYTES)
            self.assertGreater(r['nextOffset'],offset);offset=r['nextOffset'];self.assertTrue(r['captureTruncated'])
        self.assertEqual(''.join(found).encode(),raw);self.assertFalse(r['hasMore'])
        malformed=b'\xff\x00bad';r=view({**p,'rawOutputBase64':base64.b64encode(malformed).decode(),'totalBytes':len(malformed)},'output')
        self.assertEqual(base64.b64decode(r['output']['data']),malformed)

    def test_legacy_full_shape_and_readiness_unknown_classification(self):
        for profile in ('studio-tools-v13','studio-tools-v14','studio-tools-v15'):
            tool=DevelopmentTools(SimpleNamespace(config={'engine':{'profile':profile}},manifest={'projectId':'project'},session_id='session'))
            p=page();p['job'].update(kind='execution',state='running',exitCode=None,readiness={'reasonCode':'desktop_content_unconfirmed','state':'unknown'})
            r=tool.result(p['job'],p)
            self.assertFalse(r['success']);self.assertEqual(r['error'],'readiness_unknown');self.assertEqual(r['development']['jobId'],'original-job')
            if profile=='studio-tools-v15':self.assertLess(len(r['output'].encode()),LIMIT_BYTES)
            else:self.assertEqual(json.loads(r['output'])['job']['pins'],p['job']['pins'])

class ReadViewTest(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_reads_only_target_the_original_job(self):
        w=SimpleNamespace(config={'engine':{'profile':'studio-tools-v15'}},manifest={'projectId':'project'},session_id='session',run_id='10000000-0000-4000-8000-000000000043')
        tool=DevelopmentTools(w);p=page();p['job']['artifactId']=None;tool.request=AsyncMock(return_value=p)
        first=await tool.call('read_development_job',{'jobId':'original-job','view':'output'},'read-1')
        again=await tool.call('read_development_job',{'jobId':'original-job','view':'output'},'read-2')
        self.assertEqual(first,again)
        self.assertTrue(all(c.args[0]=='read_job' and c.kwargs['id']=='original-job' for c in tool.request.await_args_list))
