"""Add release-bound English contracts without changing saved prompt sources."""
import json
from pathlib import Path
from store import ProjectFault


def compose(config):
    if 'inputContractVersion' not in config:return ''
    if config['inputContractVersion']!=1:raise ProjectFault('This input instruction contract needs a compatible worker.',409)
    text='\n\n'+(Path(__file__).resolve().parents[2]/'shared/goal-attachment-instructions.txt').read_text()
    if config.get('goalExecution'):
        text+='\n\nACCEPTED HUMAN PLAY OBJECTIVE (JSON): '+json.dumps(config['goalExecution']['objective'],ensure_ascii=False)
    if config.get('attachments'):
        text+='\n\nSENT ATTACHMENT MANIFEST (task data, in Send order): '+json.dumps([
            {key:meta[key] for key in ('id','name','sha256','mediaType','mode','size')}
            for meta in config['attachments']],ensure_ascii=False)
    return text
