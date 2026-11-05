import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]/"project-development"))
import unittest,uuid
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from profile import PROFILE, tools_for
from tool_catalog import specifications,validate_arguments
from development_tools import DevelopmentTools

class ProfileTest(unittest.TestCase):
    def test_development_arguments_reject_unbound_commands_and_vm_targets(self):
        with self.assertRaises(ValueError):tools_for('unknown')
        validate_arguments('run_project',{'deploymentId':str(uuid.uuid4()),'criteria':{'outputFiles':[{'name':'RESULT.TXT','contains':'OK','sha256':None}]}})
        with self.assertRaises(ValueError):validate_arguments('run_project',{'deploymentId':str(uuid.uuid4()),'command':'foreign'})
        with self.assertRaises(ValueError):validate_arguments('capture_vm',{'jobId':str(uuid.uuid4()),'vmId':str(uuid.uuid4())})

    def test_window_control_requires_declared_arguments(self):
        current=specifications(PROFILE)
        run=next(d for d in current if d['name']=='studio_run_project')
        self.assertEqual(run['inputSchema']['properties']['windowControl']['type'],'boolean')
        self.assertNotIn('windowControl',run['inputSchema']['required'])
        validate_arguments('control_app_window',{'jobId':str(uuid.uuid4()),'action':'resize','width':640,'height':400})
        with self.assertRaises(ValueError):
            validate_arguments('control_app_window',{'jobId':str(uuid.uuid4()),'action':'restore','windowId':1})

class ImageTest(unittest.IsolatedAsyncioTestCase):
    async def test_native_image_is_transient_and_nonimage_model_causes_no_capture(self):
        worker=SimpleNamespace(config={'permissions':{'studio.capture_vm':True}},run_id=str(uuid.uuid4()))
        tool=DevelopmentTools(worker);tool.request=AsyncMock(return_value={'metadata':{'sha256':'abc'},'base64':'PNG_BYTES'})
        result={'success':True,'output':'metadata','image':{'jobId':str(uuid.uuid4()),'id':str(uuid.uuid4()),'sha256':'abc'}}
        with patch.object(tool,'image_capable',return_value=True):
            native=await tool.native_output(result)
        self.assertEqual(native['contentItems'][1],{'type':'inputImage','imageUrl':'data:image/png;base64,PNG_BYTES'})
        self.assertNotIn('PNG_BYTES',str(result));tool.request.reset_mock()
        with patch.object(tool,'image_capable',return_value=False):
            denied=await tool.call('capture_vm',{'jobId':str(uuid.uuid4())},'call')
        self.assertFalse(denied['success']);tool.request.assert_not_awaited()
