"""Skill author instructions, separate from project/global app instructions."""
import hashlib
from pathlib import Path


def snapshot():
    text = (Path(__file__).resolve().parents[2] / 'shared/default-skill-manager-prompt.txt').read_text()
    return {'revision': 0, 'source': 'default', 'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
