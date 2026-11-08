#!/usr/bin/env python3
"""Stable Root entry point for one registered session MCP instance."""
import json
import os
from pathlib import Path
import re
import stat
import sys


def main():
    if len(sys.argv)!=2 or not re.fullmatch('[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}',sys.argv[1]):
        raise SystemExit('Invalid session analysis instance.')
    config=json.loads(Path('/etc/r4os-studio-agents/config.json').read_bytes())
    path=Path(config['projects']).parent/'Skills/.mcp'/sys.argv[1]/'Launch.json'
    if path.resolve(strict=True)!=path or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size>131072:
        raise SystemExit('Invalid registered analysis instance.')
    value=json.loads(path.read_bytes())
    if value.get('schema')!=1 or value.get('serviceId')!=sys.argv[1]:raise SystemExit('The registered analysis identity changed.')
    release=Path('/opt/r4os-studio/current').resolve(strict=True)
    script=release/'scripts/agent-sessions/skill_mcp_service.py'
    if not release.is_relative_to('/opt/r4os-studio/releases') or script.resolve(strict=True)!=script:
        raise SystemExit('Invalid installed analysis controller.')
    info=script.stat()
    os.execve('/usr/bin/python3',['/usr/bin/python3','-B',str(script),sys.argv[1]],{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',
              'STUDIO_MCP_INVOCATION':os.environ.get('INVOCATION_ID','')})


if __name__=='__main__':main()
