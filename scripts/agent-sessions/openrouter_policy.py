"""Explicit OpenRouter routing/attribution; no arbitrary request/header object."""
import re
from urllib.parse import urlsplit,urlunsplit

from store import ProjectFault


def policy(value=None):
    if value is None:value={}
    if not isinstance(value,dict) or set(value)-{'order','only','allowFallbacks','attribution'}:
        raise ProjectFault('Invalid OpenRouter settings.',400)
    result={}
    for field in ('order','only'):
        entries=value.get(field,[])
        if (not isinstance(entries,list) or len(entries)>16
                or any(not isinstance(v,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_./-]{0,119}',v)
                    or any(part in ('.','..','') for part in v.split('/')) for v in entries)
                or len(set(entries))!=len(entries)):
            raise ProjectFault('Enter up to16 distinct exact OpenRouter provider slugs.',400)
        result[field]=list(entries)
    if result['only'] and any(v not in result['only'] for v in result['order']):
        raise ProjectFault('Every preferred OpenRouter provider must also be in the allowlist.',400)
    fallback=value.get('allowFallbacks',False)
    if type(fallback) is not bool:raise ProjectFault('Choose whether OpenRouter may use fallback backends.',400)
    result['allowFallbacks']=fallback
    attribution=value.get('attribution')
    if attribution is not None:
        if not isinstance(attribution,dict) or set(attribution)!={'url','title'}:
            raise ProjectFault('Configure an app URL and title together, or turn attribution off.',400)
        title=attribution['title'];url=attribution['url']
        if (not isinstance(title,str) or not 1<=len(title)<=80 or title.strip()!=title
                or any(ord(c)<32 or ord(c)>126 for c in title)
                or not isinstance(url,str) or not 1<=len(url)<=512 or any(ord(c)<33 or ord(c)>126 for c in url)):
            raise ProjectFault('Enter a bounded ASCII app URL and title for attribution.',400)
        try:
            parsed=urlsplit(url)
            if (parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username is not None
                    or parsed.password is not None or parsed.query or parsed.fragment or '\\' in url
                    or parsed.port is not None and not 1<=parsed.port<=65535):raise ValueError()
            if urlunsplit(parsed)!=url:raise ValueError()
        except ValueError:raise ProjectFault('Use an app HTTP/HTTPS URL without credentials, query or fragment.',400) from None
        attribution={'url':url,'title':title}
    result['attribution']=attribution
    return result


def unavailable(provider,model=None):
    """Chosen OpenRouter contract: plain streamed Chat with exact function history."""
    reasons=[]
    if provider['protocol']!='chat-completions':reasons.append('Use a new OpenRouter connection with Chat Completions; Responses is not qualified for this provider.')
    if provider['auth']!='bearer':reasons.append('OpenRouter requires its own bearer API key.')
    if model is not None and model['capabilities']['reasoning']!='unsupported':
        reasons.append('OpenRouter reasoning tool-history is not qualified. Choose an explicitly nonreasoning model.')
    return reasons
