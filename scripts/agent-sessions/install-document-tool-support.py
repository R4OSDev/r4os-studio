#!/usr/bin/env python3
"""Explicit document-profile compatibility; existing protocols/data preserved."""
import argparse
import importlib.util
import json
import os
from pathlib import Path

spec=importlib.util.spec_from_file_location('document_host_support',Path(__file__).with_name('install-skill-support.py'))
support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
PREVIOUS_UPDATER='40053b365b5d9b797b7cadb17ed57f90df7d01d1e2c61caf1b5e125d94156700'
PREVIOUS_DISPATCHER='2ffadc8084d7a6ce96785c013a6e2726401a6943157b44485505388b712ef8a5'


def install():
    scripts=Path(__file__).resolve().parents[1]
    updater=Path('/opt/r4os-studio/bin/update-host.py');dispatcher=updater.with_name('agent-launch.py')
    old,new=support.checked(updater,scripts/'updates/host.py',PREVIOUS_UPDATER,'document-compatible updater')
    before,after=support.checked(dispatcher,scripts/'agent-sessions/launch.py',PREVIOUS_DISPATCHER,'attachment dispatcher')
    support.idle_updater();support.control('stop','r4os-studio-updates.service')
    try:
        support.idle_updater();support.replace(updater,new,old,stamp='document-tools-v10')
        support.replace(dispatcher,after,before,stamp='document-tools-v10')
    finally:support.control('start','r4os-studio-updates.service')
    print('Document profiles10/3 and readonly rollback guard prepared; configuration, workers and VMs preserved.')


if __name__=='__main__':
    if os.getuid()!=0:raise SystemExit('Run explicit local document-tool support maintenance as root.')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--adopt',action='store_true');args=parser.parse_args()
    if args.adopt:
        release=Path('/opt/r4os-studio/current').resolve(strict=True)
        if not {'studio-tools-v10','studio-skill-tools-v3'}<=set(json.loads((release/'shared/update-host.json').read_text()).get('agentToolProfiles',[])):
            raise SystemExit('Install the immutable document-capable release before adoption.')
        support.adopt()
    else:install()
