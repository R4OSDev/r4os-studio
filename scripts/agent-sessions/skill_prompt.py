"""Skill author instructions, separate from project/global app instructions."""
from system_prompt import snapshot as prompt_snapshot


def snapshot(projects): return prompt_snapshot(projects, 'skill')
