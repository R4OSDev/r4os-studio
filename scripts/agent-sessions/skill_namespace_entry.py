"""Bring up only a new private loopback, then discard every capability."""
import ctypes
import fcntl
import os
from pathlib import Path
import socket
import struct
import subprocess
import select
import sys


def main():
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        packed=struct.pack('16sH14s',b'lo',0,b'')
        current=struct.unpack('16sH14s',fcntl.ioctl(sock.fileno(),0x8913,packed))[1]
        fcntl.ioctl(sock.fileno(),0x8914,struct.pack('16sH14s',b'lo',current|1,b''))
    libc=ctypes.CDLL(None,use_errno=True)
    # NOROOT is locked before dropping SETPCAP, so exec cannot regain caps for
    # namespace uid0. The mapped host identity remains the ordinary service user.
    if libc.prctl(28,3,0,0,0)!=0:raise OSError(ctypes.get_errno(),'Cannot seal namespace root capabilities.')
    last=int(Path('/proc/sys/kernel/cap_last_cap').read_text())
    if not 0<=last<=63:raise RuntimeError('Unsupported capability range.')
    for cap in range(last+1):
        if libc.prctl(24,cap,0,0,0)!=0:raise OSError(ctypes.get_errno(),'Cannot discard capability bounding set.')
    class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
    class Data(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
    header=Header(0x20080522,0);data=(Data*2)()
    if libc.capset(ctypes.byref(header),data)!=0 or libc.prctl(38,1,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'Cannot seal private analysis privileges.')
    if os.environ.get('STUDIO_SKILL_PROXY'):
        reader,writer=os.pipe()
        process=subprocess.Popen(['/usr/bin/python3','-I','-B','/runner/skill_net_bridge.py',str(writer)],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(writer,))
        os.close(writer)
        try:
            ready=select.select([reader],[],[],8)[0]
            if not ready or os.read(reader,5)!=b'ready':
                process.terminate();process.wait(timeout=5)
                raise RuntimeError('The private web bridge did not confirm its loopback socket.')
        finally:os.close(reader)
    if len(sys.argv)<2 or not Path(sys.argv[1]).is_absolute():raise RuntimeError('A managed absolute command is required.')
    os.execve(sys.argv[1],sys.argv[1:],dict(os.environ))


if __name__=='__main__':main()
