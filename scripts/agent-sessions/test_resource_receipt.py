import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]/'project-development'))
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from contracts import DevelopmentFault
from development_tools import DevelopmentTools

class ResourceReceipt(unittest.IsolatedAsyncioTestCase):
    async def test_original_completed_build_fetches_readonly_resource_report(self):
        pid,rid,aid=(str(uuid.uuid4()) for _ in range(3));worker=SimpleNamespace(manifest={'projectId':pid})
        tools=DevelopmentTools(worker);job={'id':rid,'kind':'build','state':'completed','artifactId':aid}
        report={'schema':1,'available':True,'stage':'Embedded','embeddedVerified':True,'guestVerified':False,'entries':[]}
        tools.request=AsyncMock(return_value={'id':aid,'buildId':rid,'projectId':pid,'entry':'APP.R4X','files':[],'resourceInventory':report,'opaque':'not public'})
        page=await tools.with_artifact(job,None);self.assertEqual(page['artifact']['resourceInventory'],report);self.assertNotIn('opaque',page['artifact']);tools.request.assert_awaited_once_with('artifact',id=aid)
    async def test_changed_owner_or_build_identity_cannot_supply_resource_proof(self):
        pid,rid,aid=(str(uuid.uuid4()) for _ in range(3));tools=DevelopmentTools(SimpleNamespace(manifest={'projectId':pid}));job={'id':rid,'kind':'build','state':'completed','artifactId':aid}
        tools.request=AsyncMock(return_value={'id':aid,'buildId':str(uuid.uuid4()),'projectId':pid})
        with self.assertRaises(DevelopmentFault):await tools.with_artifact(job,None)
        tools.request.reset_mock();self.assertIsNone(await tools.with_artifact({**job,'state':'unknown'},None));tools.request.assert_not_awaited()

if __name__=='__main__':unittest.main()
