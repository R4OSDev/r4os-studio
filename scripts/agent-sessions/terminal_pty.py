"""Acquire the controlling terminal in the already-created child session."""
import fcntl
import os
import sys
import termios

fcntl.ioctl(0, termios.TIOCSCTTY, 0)
os.execv(sys.argv[1], sys.argv[1:])
