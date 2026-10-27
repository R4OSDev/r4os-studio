"""Offline SFTP-v3 process fixture, never used by the production adapter."""
import json
from pathlib import Path
import stat
import struct
import sys

root = Path(sys.argv[1]); log = Path(sys.argv[2]); lost = '--lose-close' in sys.argv
handles = {}; sequence = 0
def u32(value): return struct.pack('>I', value)
def text(value):
    if isinstance(value, str): value = value.encode('utf8')
    return u32(len(value)) + value
def packet(value): sys.stdout.buffer.write(u32(len(value)) + value); sys.stdout.buffer.flush()
def attribute(path):
    info = path.stat(); return u32(13) + struct.pack('>Q', info.st_size) + u32(info.st_mode) + u32(1) + u32(2)
def native_path(value): return root.joinpath(*value.decode('utf8').lstrip('/').split('/'))

while header := sys.stdin.buffer.read(4):
    size = struct.unpack('>I', header)[0]; frame = memoryview(sys.stdin.buffer.read(size)); offset = 1
    def number():
        global offset
        value = struct.unpack('>I', frame[offset:offset + 4])[0]; offset += 4; return value
    def wide():
        global offset
        value = struct.unpack('>Q', frame[offset:offset + 8])[0]; offset += 8; return value
    def string():
        global offset
        length = number(); value = bytes(frame[offset:offset + length]); offset += length; return value
    kind = frame[0]
    if kind == 1: packet(bytes([2]) + u32(3)); continue
    ident = number(); reply = None; code = 0
    with log.open('a') as stream: stream.write(json.dumps({'kind': kind, 'id': ident}) + '\n')
    try:
        if kind == 7:
            if (root / '.unsupported_lstat').exists():
                packet(bytes([101]) + u32(ident) + u32(8) + text('unsupported') + text('')); continue
            value = native_path(string())
            reply = bytes([105]) + u32(ident) + attribute(value)
        elif kind in (3, 11):
            value = native_path(string()); sequence += 1; handle = str(sequence).encode()
            flags = number() if kind == 3 else 0
            if kind == 11:
                if not value.is_dir(): raise FileNotFoundError()
                handles[handle] = {'path': value, 'names': sorted(value.iterdir()), 'position': 0}
            elif flags == 1:
                handles[handle] = {'path': value, 'data': value.read_bytes(), 'write': False}
            elif flags == 58:
                if value.exists(): raise FileExistsError()
                handles[handle] = {'path': value, 'data': bytearray(), 'write': True}
            else: code = 8
            if not code: reply = bytes([102]) + u32(ident) + text(handle)
        elif kind == 5:
            entry = handles[string()]; start = wide(); count = number(); data = entry['data'][start:start + count]
            if not data: code = 1
            else: reply = bytes([103]) + u32(ident) + text(data)
        elif kind == 6:
            entry = handles[string()]; start = wide(); data = string()
            assert entry['write'] and start == len(entry['data']); entry['data'].extend(data)
        elif kind == 4:
            entry = handles.pop(string())
            if entry.get('write'):
                with entry['path'].open('xb') as stream: stream.write(entry['data'])
                if lost: raise SystemExit(255)
        elif kind == 12:
            entry = handles[string()]; selected = entry['names'][entry['position']:entry['position'] + 16]; entry['position'] += len(selected)
            if not selected: code = 1
            else: reply = bytes([104]) + u32(ident) + u32(len(selected)) + b''.join(text(p.name) + text('native listing') + attribute(p) for p in selected)
        else: code = 8
    except FileNotFoundError: code = 2
    except FileExistsError: code = 4
    if reply is None: reply = bytes([101]) + u32(ident) + u32(code) + text('fixture status') + text('')
    packet(reply)
