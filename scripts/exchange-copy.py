#!/usr/bin/env python3
"""Bound a single offline mtools extraction, including corrupt FAT chains."""
import os
import json
from pathlib import Path
import resource
import sys
maximum, image, guest, target = sys.argv[1:]
maximum = int(maximum)
limits = json.loads((Path(__file__).resolve().parents[1] / 'shared/exchange-host.json').read_text())['limits']
if not 0 <= maximum <= limits['bytes']: raise SystemExit('Invalid Exchange extraction limit.')
resource.setrlimit(resource.RLIMIT_FSIZE, (maximum, maximum))
os.execv('/usr/bin/mcopy', ['mcopy', '-i', image, guest, target])
