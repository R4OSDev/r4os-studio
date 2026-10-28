#!/usr/bin/env python3
"""Explicit image-profile compatibility, preserving existing host/data protocols."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
spec=importlib.util.spec_from_file_location('image_host_support',Path(__file__).with_name('install-skill-support.py'))
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
PREVIOUS_UPDATER='fdd95435ec4cb249f83cdb12c4a06e2506ff68c657bf6603aae6751787d9a21d'
PREVIOUS_DISPATCHER='67547907405e90ec0d794420f43f353f86670b6d72bacdb177f4cae391571140'

def install():
    scripts=Path(__file__).resolve().parents[1];updater=Path('/opt/r4os-studio/bin/update-host.py');dispatcher=updater.with_name('agent-launch.py')
    old,new=support.checked(updater,scripts/'updates/host.py',PREVIOUS_UPDATER,'image-compatible updater')
    before,after=support.checked(dispatcher,scripts/'agent-sessions/launch.py',PREVIOUS_DISPATCHER,'image dispatcher')
    support.idle_updater();support.control('stop','r4os-studio-updates.service')
    try:
        support.idle_updater();support.replace(updater,new,old,stamp='image-tools-v11')
        support.replace(dispatcher,after,before,stamp='image-tools-v11')
    finally:support.control('start','r4os-studio-updates.service')
    print('Image profiles11/4 prepared; configuration, credentials, live workers and VMs preserved.')

if __name__=='__main__':
    if os.getuid()!=0:raise SystemExit('Run explicit local image-profile maintenance as root.')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--adopt',action='store_true');args=parser.parse_args()
    if args.adopt:
        release=Path('/opt/r4os-studio/current').resolve(strict=True)
        if not {'studio-tools-v11','studio-skill-tools-v4'}<=set(json.loads((release/'shared/update-host.json').read_text()).get('agentToolProfiles',[])):
            raise SystemExit('Install the immutable image-profile release before adoption.')
        support.adopt()
    else:install()
