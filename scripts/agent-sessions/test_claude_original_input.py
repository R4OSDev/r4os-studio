"""Original public text echo: receipt identity, no premature tool admission."""
import asyncio
import copy
import unittest
import uuid

from claude_messages import acknowledge,finalize
from run_store import admit
from store import ProjectFault
from test_claude_messages import ClaudeMessages


class OriginalClaudeInput(unittest.TestCase):
    def test_exact_native_echo_is_required_and_conflicts_are_retained(self):
        f=ClaudeMessages();f.setUp();self.addCleanup(f.doCleanups)
        with f.open() as store:
            run,_=admit(store,f.sid,{'requestId':str(uuid.uuid4()),'revision':1,'text':'Own public text'},f.providers)
            w=f.receiver(store,run)
            frame={'native':{'type':'user','isReplay':True,'session_id':f.native},'identity':{
                'nativeType':'user','nativeSessionId':f.native,'nativeInputRequestIds':[w.row['request_id']],
                'nativeMessageId':w.row['request_id'],'nativeInputReceiptKind':'stdinEcho',
                'nativeInputTextSha256':w.config['claudeInput']['textSha256']}}
            self.assertFalse(acknowledge(w,f.frame(w)));self.assertFalse(w.input_receipt.is_set())
            wrong=copy.deepcopy(frame);wrong['identity']['nativeInputTextSha256']='0'*64
            with self.assertRaises(ProjectFault):acknowledge(w,wrong)
            self.assertTrue(acknowledge(w,frame));self.assertTrue(acknowledge(w,frame))
            self.assertTrue(w.input_receipt.is_set())
            self.assertEqual(store.db.execute('SELECT count(*) FROM claude_input_receipts').fetchone()[0],1)
            w.input_receipt=asyncio.Event();w.sent=True;finalize(w)
            self.assertEqual(w.outcome,'unknown');self.assertTrue(w.uncertain_effect)
