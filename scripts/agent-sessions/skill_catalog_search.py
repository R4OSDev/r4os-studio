"""Literal discovery in one frozen verified metadata catalogue; never an MCP call."""
import base64
import json
from skill_mcp_client import McpFault, encoded, strict


def search(entry, kind, values, args):
    query = args.get('query')
    if (kind not in ('tools', 'prompts') or not isinstance(query, str) or not query.strip()
        or len(query.encode('utf-8')) > 160 or any(k in args for k in ('name', 'offset', 'schemaOffset'))):
        raise McpFault('Search requires skillId, tools/prompts and a literal query of 1–160 UTF-8 bytes, without name/offset/schemaOffset.')
    binding = dict(version=1, skillId=entry['id'], revision=entry['revision'], activeRevision=entry['activeRevision'],
        packageHash=entry['activeHash'], catalogueHash=entry['mcp']['catalogHash'], kind=kind, query=query)
    offset=0; limit=args.get('limit',12)
    if type(limit) is not int or not 1 <= limit <= 12: raise McpFault('Choose a discovery limit from 1 to 12.')
    if args.get('searchCursor') is not None:
        try:
            cursor=args['searchCursor']
            if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
            value=strict(base64.urlsafe_b64decode(cursor+'='*((-len(cursor))%4)))
            if (not isinstance(value,dict) or any(value.get(k)!=v for k,v in binding.items())
                or type(value.get('offset')) is not int or value['offset']<1):raise ValueError()
            offset=value['offset']
        except (ValueError,TypeError):raise McpFault('The search cursor belongs to another skill revision, catalogue, kind or literal query. Start that search again; no native call was sent.') from None
    needle=query.casefold()
    matched=[v for v in values if any(isinstance(v.get(key),str) and needle in v[key].casefold() for key in ('name','description'))]
    if offset>len(matched):raise McpFault('This search continuation is outside its original matches.')
    selected=matched[offset:offset+limit];end=offset+len(selected)
    following=base64.urlsafe_b64encode(encoded({**binding,'offset':end})).decode().rstrip('=') if end<len(matched) else None
    return {**binding,'items':[dict(name=v.get('name'),title=v.get('title'),descriptionPreview=v.get('description','')[:600]) for v in selected],
        'total':len(values),'matches':len(matched),'offset':offset,'nextCursor':following,'complete':True,
        'search':'case-insensitive literal name/description substring',
        'fullSchemas':'Choose an exact returned name without query/searchCursor. Read every schema page with studio_read_skill_result reference/nextOffset before invoking. Search results are orientation only.'}


def orientation(value, page):
    schema=value.get('inputSchema') or {}
    required=schema.get('required',[])
    if not isinstance(required,list):required=[]
    shown=[name for name in required if isinstance(name,str) and len(name.encode('utf-8'))<=128][:16]
    return dict(orientationOnly=True,topLevelRequired=shown,additionalRequiredFields=max(0,len(required)-len(shown)),
        branchDependent=any(k in schema for k in ('oneOf','anyOf','allOf','if','$ref')),
        notice='Orientation only; native unions, nulls, defaults and descriptions remain in the complete unchanged schema.',
        fullSchema=dict(reference=page['reference'],sha256=page['sha256'],bytes=page['bytes'],nextOffset=page['nextOffset'],
            readTool='studio_read_skill_result',instruction='If complete=false, continue from nextOffset until complete=true and verify the same sha256. Do not infer omitted fields from this preview.'))
