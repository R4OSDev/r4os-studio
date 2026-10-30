#!/usr/bin/env python3
"""Only this model namespace may lift its inherited soft history-file bound."""
import os
import resource
import sys


if __name__=='__main__':
    if os.getuid()==0 or len(sys.argv)<2:raise SystemExit(1)
    _,hard=resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE,(hard,hard))
    # Arguments come only from the fixed trusted worker namespace builder.
    # The project-tool namespace retains its separate256MiB hard bound.
    os.execv('/usr/bin/bwrap',['/usr/bin/bwrap',*sys.argv[1:]])
