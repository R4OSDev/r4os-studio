"""Explicit assertions; process acceptance/window visibility never imply pass."""
import base64
from pathlib import Path


def evaluate(settings, state, output, files=(), visual=None):
    criteria = {'expectedExitCode': settings.get('expectedExitCode'), 'outputContains': settings.get('outputContains', []),
        'outputFiles': settings.get('outputFiles', []), 'serviceResponseContains': settings.get('serviceResponseContains'),
        'visual': settings.get('visualCriteria', '')}
    configured = criteria['expectedExitCode'] is not None or any(criteria[k] for k in ('outputContains', 'outputFiles', 'serviceResponseContains', 'visual'))
    findings = []; unknown = False; failed = False; evidence_ids = [f['id'] for f in files if f.get('id')]
    if not configured: return {'state': 'not-run', 'criteria': criteria, 'findings': [], 'evidenceIds': [], 'assessment': None}
    done = state.get('state') == 'completed'
    expected = criteria['expectedExitCode']
    if expected is not None:
        if not done or state.get('exitCode') is None: unknown = True; findings.append('Expected exit status is not confirmed.')
        elif state['exitCode'] != expected: failed = True; findings.append('The exit code differs from the expected value.')
    text = output.decode('utf-8', errors='replace')
    for needle in criteria['outputContains']:
        if needle not in text:
            if done and not state.get('outputIncomplete'): failed = True; findings.append('Expected console output is missing: ' + needle)
            else: unknown = True
    if state.get('outputIncomplete') and criteria['outputContains']: unknown = True; findings.append('Console output is incomplete.')
    indexed = {value['name']: value for value in files}
    for expected_file in criteria['outputFiles']:
        actual = indexed.get(expected_file['name'])
        if not actual:
            if done: failed = True; findings.append('A registered output file is missing: ' + expected_file['name'])
            else: unknown = True
            continue
        if actual.get('error'): unknown = True; findings.append(actual['error']); continue
        if expected_file['sha256'] and actual['sha256'] != expected_file['sha256']:
            failed = True; findings.append('Output checksum differs: ' + expected_file['name'])
        if expected_file['contains'] is not None and not actual.get('containsExpectedText'):
            failed = True; findings.append('Expected file text is missing: ' + expected_file['name'])
    if criteria['serviceResponseContains']:
        if state.get('serviceCheckPassed') is None: unknown = True; findings.append('The service self-test has not completed.')
        elif not state['serviceCheckPassed']: failed = True; findings.append('The service self-test did not return a successful response.')
        else:
            try: response = base64.b64decode(state.get('serviceResponseBase64', ''), validate=True).decode('utf-8')
            except (ValueError, UnicodeDecodeError): response = ''
            if criteria['serviceResponseContains'] not in response: failed = True; findings.append('The service response differs from the expected text.')
    assessment = 'host'
    if criteria['visual']:
        if not visual: unknown = True; findings.append('Visual criteria need an image-backed agent assessment.')
        else:
            assessment = visual.get('actor', 'agent')
            evidence_ids.append(visual['evidenceId'])
            if visual['state'] == 'failed': failed = True
            elif visual['state'] != 'passed': unknown = True
            findings.append(visual['notes'])
    if state.get('stopReason') in ('timeout', 'control_lost'): failed = True; findings.append('Execution exceeded a runtime or control limit.')
    result = 'failed' if failed else ('inconclusive' if unknown else 'passed')
    return {'state': result, 'criteria': criteria, 'findings': findings[:20], 'evidenceIds': evidence_ids, 'assessment': assessment}
