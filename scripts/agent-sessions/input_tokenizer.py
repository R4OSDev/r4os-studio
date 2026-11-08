"""Qualified offline tokenizer and bounded worker-local text cache."""
from functools import lru_cache
import base64
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[2]/'vendor/tokenizer'
MANIFEST_SHA256='f9a538c364878aedde70b8fdb6df5a7430124aa176b96dbe6e041b1bd44d190e'
PROFILE={'version':2,'method':'local-tokenizer-v1','libraryVersion':'0.14.0','manifestSha256':MANIFEST_SHA256}
MAX_CACHED_TEXT=256*1024


@lru_cache(maxsize=1)
def manifest():
    raw=(ROOT/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA256:raise ValueError('Tokenizer manifest changed')
    return json.loads(raw)


def select(binding,profile):
    if profile!=PROFILE:raise ValueError('Unknown accepted tokenizer profile')
    # An OpenAI-compatible wire or a familiar model name does not establish
    # that a custom backend uses the same tokenizer.
    official=binding.get('baseUrl')=='https://api.openai.com/v1' and binding.get('kind')=='openai-compatible'
    native=binding.get('kind')=='codex-subscription' and binding.get('baseUrl')=='https://chatgpt.com/backend-api/codex'
    if not (official or native):return None,'No qualified tokenizer mapping for this model connection.'
    try:
        for name,value in manifest()['encodings'].items():
            if binding.get('model') in value['modelNames']:return name,None
    except (OSError,ValueError,KeyError):return None,'The pinned tokenizer manifest is unavailable; Unicode fallback used.'
    return None,'The exact model ID has no verified mapping in tiktoken 0.14.0; Unicode fallback used.'


@lru_cache(maxsize=1)
def library():
    if (sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,13)
            or sys.platform!='linux' or platform.machine()!='x86_64'):
        raise ImportError('The bundled tokenizer does not target this worker platform')
    for name,expected in manifest()['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('Tokenizer asset changed')
    old=sys.modules.get('tiktoken')
    if old is not None and Path(old.__file__).resolve()!=(ROOT/'tiktoken/__init__.py').resolve():
        raise ImportError('An unrelated tokenizer library is already loaded')
    path=str(ROOT)
    if path not in sys.path:sys.path.insert(0,path)
    module=importlib.import_module('tiktoken')
    if module.__version__!='0.14.0':raise ValueError('Tokenizer version changed')
    return module


@lru_cache(maxsize=2)
def encoding(name):
    package=library();facts=manifest()['encodings'][name]
    raw=gzip.decompress((ROOT/facts['file']).read_bytes())
    if hashlib.sha256(raw).hexdigest()!=facts['rawSha256']:raise ValueError('Tokenizer table changed')
    ranks={base64.b64decode(token,validate=True):int(rank) for token,rank in (line.split() for line in raw.splitlines())}
    return package.Encoding(name,pat_str=facts['pattern'],mergeable_ranks=ranks,special_tokens=facts['specialTokens'])


def scope(binding):
    value={key:binding.get(key) for key in ('id','model','kind','baseUrl','protocol','revision','credentialRevision')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@lru_cache(maxsize=32)
def cached_count(name,binding_scope,text):
    return len(encoding(name).encode_ordinary(text))


def count(name,binding,text):
    # Maximum 32 * 256 KiB retained texts, independently of conversation size.
    if len(text.encode())<=MAX_CACHED_TEXT:return cached_count(name,scope(binding),text)
    return len(encoding(name).encode_ordinary(text))
