#!/usr/bin/env python3
"""Explicit additive private project job path; no bootstrap/unit replacement."""
import json
import os
from pathlib import Path
import subprocess


def main():
    if os.geteuid() != 0: raise SystemExit('Run local host setup as Root.')
    print('Root services already have access to their configured data paths. No filesystem grant is needed.')


if __name__ == '__main__': main()
