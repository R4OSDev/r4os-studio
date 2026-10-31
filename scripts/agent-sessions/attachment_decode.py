"""Decode only an owned pending upload, outside the web service's inherited filters."""
import hashlib
import json
import socket

from attachment_store import Attachments, MAX_FILE, decode_image, decode_pdf
from owner import binding
from profile import regular
from session_store import identity, encode
from store import ProjectFault

UNAVAILABLE = 'Attachment validation is unavailable. The isolated decoder could not be reached; this is a Studio service problem.'


def request_decode(store, sid, ident, socket_path):
    request = {'operation': 'decode_pending_attachment', 'projects': str(store.projects.absolute()),
               'ownerType': store.owner_type, 'ownerId': store.owner_id,
               'sessionId': identity(sid), 'attachmentId': identity(ident)}
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(18); client.connect(socket_path)
            client.sendall((encode(request) + '\n').encode()); client.shutdown(socket.SHUT_WR)
            with client.makefile('rb') as stream: raw = stream.readline(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024 or not raw.endswith(b'\n'): raise ValueError()
        value = json.loads(raw)
        if 'error' in value:
            raise ProjectFault(value['error'], value['code'])
        if set(value) != {'result'} or not isinstance(value['result'], dict): raise ValueError()
        return value['result']
    except (OSError, ValueError, KeyError, TypeError):
        raise ProjectFault(UNAVAILABLE, 503) from None


def decode_pending(host, request):
    if set(request) != {'operation', 'projects', 'ownerType', 'ownerId', 'sessionId', 'attachmentId'}:
        raise ProjectFault('Unexpected attachment validation fields.', 400)
    if request['projects'] != host.config['projects']:
        raise ProjectFault('Attachment storage binding changed.', 409)
    kind, owner = binding(request)
    store = host.store(owner, kind)
    try:
        attachments = Attachments(store, identity(request['sessionId']))
        row = attachments.row(identity(request['attachmentId']))
        if row['state'] != 'pending': raise ProjectFault('Only a pending upload can be validated.', 409)
        meta = json.loads(row['metadata'])
        if type(meta['size']) is not int or not 0 < meta['size'] <= MAX_FILE:
            raise ProjectFault('Invalid pending attachment size.', 409)
        path = regular(attachments.root() / row['id'] / 'original.uploading')

        def verify():
            if path.stat().st_size != meta['size']:
                raise ProjectFault('Pending attachment bytes changed before validation.', 409)
            with regular(path).open('rb') as stream: raw = stream.read(MAX_FILE + 1)
            if len(raw) != meta['size'] or hashlib.sha256(raw).hexdigest() != meta['sha256']:
                raise ProjectFault('Pending attachment bytes changed before validation.', 409)
            return raw[:16]

        head = verify()
        if head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8') or (head[:4] == b'RIFF' and head[8:12] == b'WEBP'):
            result = decode_image(path)
        elif head.startswith(b'%PDF-'):
            result = decode_pdf(path)
        else:
            raise ProjectFault('This upload does not need an isolated binary decoder.', 400)
        verify()
        return result
    finally:
        store.close()
