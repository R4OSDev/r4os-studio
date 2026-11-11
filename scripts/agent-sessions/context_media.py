"""Select superseded tool screenshots without changing any original record."""
import base64
from collections import OrderedDict
import hashlib
import json

from store import ProjectFault


def purpose(name, arguments):
    if (name=='studio_read_context_result' or name=='studio_read_result' and arguments.get('action') in ('context','image','index')
            or name=='studio_capture_vm' and arguments.get('action')=='inspect'):
        return 'historical'
    if name=='studio_capture_vm':
        return 'comparison' if 'analysisQuestion' in arguments else 'capture'
    return 'tool'


def delivered(body, call, ref, sha):
    """Require the original result binding and its exact pixels in that input."""
    pixels = []; original = False
    pending = [body.get('input', body.get('messages', []))]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        if not isinstance(value, dict):
            continue
        kind = value.get('type')
        if kind in ('input_image','image_url'):
            url=value.get('image_url')
            if isinstance(url,dict):url=url.get('url')
            if isinstance(url,str) and url.startswith('data:image/png;base64,'):
                pixels.append(url.split(',',1)[1])
        if kind=='image' and isinstance(value.get('source'),dict) and value['source'].get('media_type')=='image/png':
            pixels.append(value['source'].get('data'))
        text = None
        if kind=='function_call_output' and value.get('call_id')==call:text=value.get('output')
        elif value.get('role')=='tool' and value.get('tool_call_id')==call:text=value.get('content')
        elif kind=='tool_result' and value.get('tool_use_id')==call:text=value.get('content')
        if isinstance(text,list):
            text=next((p.get('text') for p in text if isinstance(p,dict) and p.get('type')=='text'),None)
        if isinstance(text,str):
            try: result=json.loads(text)
            except ValueError: result=None
            original=original or (isinstance(result,dict) and result.get('screenshotReference')==ref
                and result.get('imageDelivery')=='pixels' and (result.get('image') or {}).get('sha256')==sha)
        pending.extend(p for p in value.values() if isinstance(p,(dict,list)))
    if original:
        for data in pixels:
            try:
                if hashlib.sha256(base64.b64decode(data,validate=True)).hexdigest()==sha:return True
            except (ValueError,TypeError):pass
    return False


class Screenshots:
    def __init__(self, worker):
        self.w = worker
        self.proofs = OrderedDict()

    def captured(self, record):
        from context_results import load, reference, settled
        parts = record['content']
        if record['role'] != 'tool' or len(parts) != 2 or [p['type'] for p in parts] != ['tool_result','image']:
            return None
        result = parts[0]['result']; image = result.get('image')
        ref = result.get('screenshotReference')
        if (not isinstance(image,dict) or result.get('imageDelivery')!='pixels' or ref!=parts[1].get('reference')
                or image.get('kind')!='screenshot' or result.get('captureState')!='confirmed' or not settled(result)):
            return None
        try:
            _,_,tool=load(self.w, reference(self.w,record,0))
            if tool['state']!='completed' or tool['tool']!='studio_capture_vm':return None
            row=self.w.store.db.execute('SELECT intent FROM tools WHERE run_id=? AND call_id=?',
                (record['runId'],record['origin']['toolReceiptId'])).fetchone()
            args=json.loads(row['intent'])
            if (args.get('action','capture')!='capture' or args.get('jobId')!=image.get('jobId')
                    or purpose(tool['tool'],args)!='capture' or record['origin'].get('mediaPurpose','capture')!='capture'):
                return None
            return (record['runId'], image['jobId'], image['scope'], image.get('vmId')), image
        except (ProjectFault, KeyError, ValueError, TypeError):
            return None

    def processed(self, response, call, ref, sha):
        key = (response['id'], call, ref, sha)
        if key not in self.proofs:
            from history_receipts import original_input
            body = original_input(self.w.store, self.w.session_id, response)
            self.proofs[key] = isinstance(body,dict) and delivered(body,call,ref,sha)
            if len(self.proofs)>128:self.proofs.popitem(last=False)
        return self.proofs[key]

    def retired(self, active, retained):
        # An explicit use of the original frame for input establishes its role
        # as the preceding live frame. Comparisons and historical reads may
        # use the same image bytes but are never retirement candidates.
        from context_results import has_uncertain_result
        later = {}; uses = {}; results = {}; retired = set()
        for record in reversed(active):
            if record['role']=='tool':
                for part in record['content']:
                    if part['type']=='tool_result':
                        results[(record.get('runId'),part['callId'])]=record
            if record['role']=='assistant' and record.get('origin',{}).get('providerResponseId'):
                for part in record['content']:
                    if part['type']!='tool_call' or part['name']!='studio_send_vm_input':
                        continue
                    outcome=results.get((record['runId'],part['callId']))
                    args=part['arguments']
                    if outcome and isinstance(args.get('frameId'),str) and not has_uncertain_result(outcome):
                        uses[(record['runId'],args.get('jobId'),args['frameId'])]=record
            candidate=self.captured(record)
            if candidate is None:continue
            slot,image=candidate
            new=later.setdefault(slot,record)
            seq=record['sequence']
            if new is record or seq in retained or record['origin'].get('turnId')==new['origin'].get('turnId'):
                continue
            used=uses.get((record['runId'],image['jobId'],image['id']))
            part=record['content'][0]
            if used and used['sequence']<new['sequence'] and self.processed(used,part['callId'],
                    part['result']['screenshotReference'],image['sha256']):
                retired.add(seq)
        return retired
