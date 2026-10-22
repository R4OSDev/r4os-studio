"""Small explicit Run & Test contract; no arbitrary runner/shell selection."""
import re
from contracts import DevelopmentFault, encode

DEFAULTS = {'outputFiles': [], 'serviceResponseContains': None}


def validate(value):
    expected = {'revision', 'arguments', 'workingDirectory', 'timeoutSeconds', 'expectedExitCode',
        'outputContains', 'visualCriteria', 'outputFiles', 'serviceResponseContains'}
    if not isinstance(value, dict) or set(value) != expected: raise DevelopmentFault('Unexpected Run & Test fields.', 400)
    def string(v, maximum):
        return isinstance(v, str) and '\x00' not in v and len(v.encode()) <= maximum
    if type(value['revision']) is not int or value['revision'] < 1: raise DevelopmentFault('Invalid settings revision.', 400)
    if not string(value['arguments'], 1024): raise DevelopmentFault('Arguments exceed their limit.', 400)
    if value['workingDirectory'] != '.': raise DevelopmentFault('Use the deployment working directory.', 400)
    if type(value['timeoutSeconds']) is not int or not 1 <= value['timeoutSeconds'] <= 300: raise DevelopmentFault('Choose a time limit from 1 to 300 seconds.', 400)
    exit_code = value['expectedExitCode']
    if exit_code is not None and (type(exit_code) is not int or not -2147483648 <= exit_code <= 2147483647): raise DevelopmentFault('Invalid expected exit code.', 400)
    output = value['outputContains']
    if not isinstance(output, list) or len(output) > 8 or any(not string(v, 256) or not v for v in output): raise DevelopmentFault('Invalid output criteria.', 400)
    if not string(value['visualCriteria'], 1024): raise DevelopmentFault('Visual criteria exceed their limit.', 400)
    files = value['outputFiles']
    if not isinstance(files, list) or len(files) > 8: raise DevelopmentFault('Register at most eight output files.', 400)
    names = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {'name', 'contains', 'sha256'}: raise DevelopmentFault('Invalid output file criterion.', 400)
        name = item['name']
        if not isinstance(name, str) or not re.fullmatch(r'[A-Z0-9_]{1,8}\.[A-Z0-9_]{1,3}', name) or name in names:
            raise DevelopmentFault('Use unique uppercase 8.3 output filenames in the deployment directory.', 400)
        if re.fullmatch(r'[QA][A-F0-9]{7}\.JSN', name): raise DevelopmentFault('A control file cannot be a test output.', 400)
        if name in ('APP.R4X', 'STHELP.R4X', 'STWATCH.R4X', 'PACKAGE.JSN'): raise DevelopmentFault('A package file cannot be a test output.', 400)
        names.add(name)
        if item['contains'] is not None and not string(item['contains'], 1024): raise DevelopmentFault('Invalid output file text criterion.', 400)
        if item['sha256'] is not None and (not isinstance(item['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', item['sha256'])): raise DevelopmentFault('Invalid output file checksum.', 400)
    if value['serviceResponseContains'] is not None and (not string(value['serviceResponseContains'], 256) or not value['serviceResponseContains']):
        raise DevelopmentFault('Enter the expected service self-test response.', 400)
    return value


def update(store, value):
    value = validate(value)
    if store.project['template'] == 'service' and len(value['arguments'].encode()) > 95: raise DevelopmentFault('Service arguments are limited to 95 bytes.', 400)
    if value['serviceResponseContains'] is not None and store.project['template'] != 'service': raise DevelopmentFault('This project is not a service.', 400)
    store.db.execute('BEGIN IMMEDIATE')
    try:
        if value['revision'] != store.settings()['revision']: raise DevelopmentFault('Run & Test settings changed. Reload before saving.')
        if store.db.execute('SELECT id FROM jobs WHERE busy=1').fetchone(): raise DevelopmentFault('Stop this project development job before changing Run & Test settings.')
        result = {**value, 'revision': value['revision'] + 1}
        store.db.execute('UPDATE settings SET payload=? WHERE id=1', (encode(result),)); store.db.commit(); return result
    except BaseException: store.db.rollback(); raise
