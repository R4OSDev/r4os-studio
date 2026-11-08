#!/usr/bin/env python3
"""Only this native model process may lift its inherited soft history-file bound."""
import os
import resource
import sys


if __name__=='__main__':
    if len(sys.argv)<2:raise SystemExit(1)
    _,hard=resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE,(hard,hard))
    # Arguments come only from the fixed worker launcher.
    os.execv(sys.argv[1],sys.argv[1:])
