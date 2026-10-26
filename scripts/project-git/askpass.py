#!/usr/bin/python3
"""Credential answer for this worker's exact GitHub HTTPS transport only."""
import socket
import sys

if len(sys.argv) != 2 or not sys.argv[1].startswith(('Username for ', 'Password for ')):
    raise SystemExit(1)
prompt = sys.argv[1]
if 'https://github.com' not in prompt and 'https://x-access-token@github.com' not in prompt:
    raise SystemExit(1)
with socket.socket(socket.AF_UNIX) as client:
    client.settimeout(3); client.connect('/credential.sock')
    client.sendall(('username' if prompt.startswith('Username') else 'password').encode())
    raw = client.recv(8192)
    if not raw or b'\n' in raw or b'\r' in raw: raise SystemExit(1)
    sys.stdout.buffer.write(raw + b'\n')
