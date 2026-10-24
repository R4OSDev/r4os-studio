#!/usr/bin/env python3
"""Bound a single offline mtools extraction, including corrupt FAT chains."""
import os
import resource
import sys
maximum, image, guest, target = sys.argv[1:]
maximum = int(maximum)
if not 0 <= maximum <= 96 * 1024 * 1024: raise SystemExit('Invalid Exchange extraction limit.')
resource.setrlimit(resource.RLIMIT_FSIZE, (maximum, maximum))
os.execv('/usr/bin/mcopy', ['mcopy', '-i', image, guest, target])
