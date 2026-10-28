import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from contracts import DevelopmentFault
from resource_inventory import inspect

# Fixed minimal R4M0/1 resource-directory contract fixture. Full native
# inspector/language-artifact qualification is recorded in Research0.6.46.
HEADER=bytes.fromhex('52344d300100010001004000010000004000000001000000'+'00'*40)
SECTION=bytes.fromhex('2e72737263000000000000006000000024000000240000001000000000000000')
RESOURCE=bytes.fromhex('01000000 03000000 14000000 20000000 04000000 5343454e4500 000000000000 01020380')
class ResourceInventory(unittest.TestCase):
    def test_exact_payload_identity_and_separate_guest_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);asset=root/'Pixels.rgba';asset.write_bytes(bytes.fromhex('01020380'));binary=root/'App.R4X';binary.write_bytes(HEADER+SECTION+RESOURCE)
            inputs={'available':True,'sourceSha256':'a'*64,'manifestSha256':'b'*64,'entries':[{'kind':'file','index':0,'name':'SCENE','path':'Pixels.rgba','bytes':4,'sha256':hashlib.sha256(asset.read_bytes()).hexdigest()}]}
            result=inspect(binary,inputs,root);self.assertTrue(result['embeddedVerified']);self.assertFalse(result['consumerVerified']);self.assertFalse(result['guestVerified']);self.assertEqual(result['entries'][0]['sha256'],inputs['entries'][0]['sha256'])
            correct=binary.read_bytes();changed=bytearray(correct);changed[-1]^=1;binary.write_bytes(changed)
            with self.assertRaises(DevelopmentFault):inspect(binary,inputs,root)
            binary.write_bytes(correct)
            asset.write_bytes(b'edit')
            with self.assertRaises(DevelopmentFault):inspect(binary,inputs,root)
    def test_out_of_bounds_and_corrupt_directories_cannot_claim_embedding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);binary=root/'App.R4X';inputs={'available':True,'entries':[]}
            for offset in (20,64+12,96,96+4+8):
                raw=bytearray(HEADER+SECTION+RESOURCE);struct.pack_into('<I',raw,offset,0xffffffff);binary.write_bytes(raw)
                with self.assertRaises(DevelopmentFault):inspect(binary,inputs,root)
    def test_old_catalog_remains_unknown_without_reading_file(self):self.assertFalse(inspect(Path('/not-read'),{'available':False},Path('/not-read'))['available'])
if __name__=='__main__':unittest.main()
