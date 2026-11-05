"""Documented defaults, not a model allowlist or proof of account entitlement."""
import copy
import json
from pathlib import Path


def documented(protocol='chat-completions'):
    value=json.loads((Path(__file__).resolve().parents[2]/'shared/zai-models.json').read_text())
    result=[{**copy.deepcopy(model['facts']), 'source':{'kind':'metadata','recordedAt':value['recordedAt'],
             'url':model['url']}} for model in value['models']]
    if protocol=='messages':
        for model in result:
            model['messages']={'apiVersion':'2023-06-01','thinkingType':'enabled','thinkingDisabled':model['reasoning'].get('mandatory') is not True}
    return result
