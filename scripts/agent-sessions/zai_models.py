"""Documented defaults, not a model allowlist or proof of account entitlement."""
import copy
import json
from pathlib import Path


def documented():
    value=json.loads((Path(__file__).resolve().parents[2]/'shared/zai-models.json').read_text())
    return [{**copy.deepcopy(model['facts']), 'source':{'kind':'metadata','recordedAt':value['recordedAt'],
             'url':model['url']}} for model in value['models']]
