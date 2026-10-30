"""Explicit server contracts; never infer a vendor from an address/model name."""
from store import ProjectFault

SERVERS=('custom','ollama','lm-studio')


def server(value='custom'):
    if not isinstance(value,str) or value not in SERVERS:
        raise ProjectFault('Choose Custom, Ollama or LM Studio as the API server contract.',400)
    return value


def unavailable(provider,model=None):
    if provider.get('server','custom')=='custom':return []
    reasons=[]
    if model is not None:
        if model['capabilities']['reasoning']!='unsupported':
            reasons.append('This server adapter requires an explicitly nonreasoning model; reasoning history is not qualified.')
        if model['contextWindow'] is None:
            reasons.append('Confirm the actual server-configured context window, not only the model maximum.')
    return reasons
