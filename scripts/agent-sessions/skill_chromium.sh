#!/bin/sh
set -eu
exec /usr/bin/python3 -I -B /runner/skill_browser_launch.py "$@"
