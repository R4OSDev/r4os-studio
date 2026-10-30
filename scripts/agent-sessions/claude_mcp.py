#!/usr/bin/env python3
"""Fixed stdio MCP tool transport. No credentials, shell, files or HTTP tools."""
import json
from pathlib import Path
import re
import socket
import sys

MAX_REQUEST=262144
MAX_RESULT=16*1024*1024
PROTOCOLS=('2024-11-05','2025-03-26','2025-06-18','2025-11-25')


def identifier(value):
    return isinstance(value,str) and 0<len(value.encode())<=256 and not any(ord(c)<=32 or ord(c)==127 for c in value)


class McpFault(Exception):
    def __init__(self,code,message):super().__init__(message);self.code=code


def mcp_schema(value):
    """Keep union contracts inside a named argument; native MCP omits root unions."""
    if not isinstance(value,dict):raise ValueError('Invalid frozen tool schema.')
    branches=value.get('oneOf') or value.get('anyOf')
    if isinstance(branches,list) and branches and all(isinstance(v,dict) and v.get('type')=='object' for v in branches):
        # Original #/$defs references retain their original absolute location.
        # The host still validates the exact untouched Studio argument object.
        return {'type':'object','properties':{'request':value},'required':['request'],'additionalProperties':False,
            **({'$defs':value['$defs']} if '$defs' in value else {})}
    if value.get('type')=='object':return value
    raise ValueError('This tool schema cannot be represented as an MCP object.')


class StudioMcp:
    def __init__(self,config,broker):
        if (not isinstance(config,dict) or set(config)!={'schema','binding','tools'} or type(config['schema']) is not int or config['schema']!=1
            or not isinstance(config['binding'],dict) or not isinstance(config['tools'],list) or len(config['tools'])>128):
            raise ValueError('Invalid frozen MCP configuration.')
        self.binding=config['binding'];self.broker=broker;self.ready=False;self.tools={};self.enveloped=set()
        for tool in config['tools']:
            if (not isinstance(tool,dict) or set(tool)!={'name','description','inputSchema'}
                or not isinstance(tool['name'],str) or not re.fullmatch('[a-z][a-z0-9_]{0,79}',tool['name'])
                or tool['name'] in self.tools or not isinstance(tool['description'],str) or len(tool['description'])>16000
                or not isinstance(tool['inputSchema'],dict)):
                raise ValueError('Invalid frozen MCP tool.')
            converted=mcp_schema(tool['inputSchema'])
            wrapped=converted is not tool['inputSchema']
            if wrapped:self.enveloped.add(tool['name'])
            self.tools[tool['name']]={**tool,'inputSchema':converted,
                '_meta':{'anthropic/alwaysLoad':True,'anthropic/maxResultSizeChars':1048576},
                'description':tool['description']+(' Put the complete original Studio argument object in request.' if wrapped else '')}

    def handle(self,value):
        if (not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or not isinstance(value.get('method'),str)
            or set(value)-{'jsonrpc','id','method','params'} or 'id' in value and (type(value['id']) not in (str,int))):
            raise McpFault(-32600,'Invalid bounded MCP request.')
        method=value['method'];params=value.get('params',{})
        if not isinstance(params,dict):raise McpFault(-32602,'Invalid MCP parameters.')
        if 'id' not in value:
            if method in ('notifications/initialized','notifications/cancelled'):return None
            raise McpFault(-32601,'This MCP notification is unavailable.')
        if method=='initialize':
            protocol=params.get('protocolVersion')
            if not isinstance(protocol,str):raise McpFault(-32602,'A protocol version is required.')
            self.ready=True
            return {'protocolVersion':protocol if protocol in PROTOCOLS else PROTOCOLS[-1],
                'capabilities':{'tools':{'listChanged':False}},'serverInfo':{'name':'r4os-studio','version':'1.0.0'}}
        if not self.ready:raise McpFault(-32002,'Initialize this bound MCP transport first.')
        if method=='ping':return {}
        if method=='tools/list':
            if params:raise McpFault(-32602,'This frozen tool list has no cursor or filters.')
            return {'tools':list(self.tools.values())}
        if method!='tools/call':raise McpFault(-32601,'Only the frozen Studio tool methods are available.')
        if set(params)-{'name','arguments','_meta'} or not isinstance(params.get('name'),str) or params.get('name') not in self.tools or not isinstance(params.get('arguments'),dict):
            raise McpFault(-32602,'This call is outside the frozen Studio tool list.')
        meta=params.get('_meta');call_id=meta.get('claudecode/toolUseId') if isinstance(meta,dict) else None
        if not identifier(call_id):raise McpFault(-32602,'The original native tool-use identity is required.')
        arguments=params['arguments']
        if params['name'] in self.enveloped:
            if set(arguments)!={'request'} or not isinstance(arguments['request'],dict):raise McpFault(-32602,'This tool requires its complete original argument object in request.')
            arguments=arguments['request']
        result=self.broker({'operation':'call','binding':self.binding,'tool':params['name'],
            'nativeToolUseId':call_id,'arguments':arguments})
        if (not isinstance(result,dict) or set(result)-{'content','isError'} or type(result.get('isError')) is not bool
            or not isinstance(result.get('content'),list) or not 1<=len(result['content'])<=16):
            raise McpFault(-32603,'The original Studio tool result is unconfirmed; do not repeat the effect.')
        for block in result['content']:
            if not isinstance(block,dict):raise McpFault(-32603,'Invalid original tool content.')
            if block.get('type')=='text' and set(block)=={'type','text'} and isinstance(block['text'],str):continue
            if (block.get('type')=='image' and set(block)=={'type','mimeType','data'} and block['mimeType']=='image/png'
                and isinstance(block['data'],str) and re.fullmatch('[A-Za-z0-9+/]*={0,2}',block['data'])):continue
            raise McpFault(-32603,'The original Studio tool content is unavailable.')
        return result


def broker(value):
    data=json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()+b'\n'
    if len(data)>MAX_REQUEST:raise McpFault(-32602,'Tool arguments exceed the bound.')
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(1210);client.connect('/bridge/host.sock');client.sendall(data);client.shutdown(socket.SHUT_WR)
            with client.makefile('rb') as stream:raw=stream.readline(MAX_RESULT+1)
        if not raw.endswith(b'\n') or len(raw)>MAX_RESULT:raise ValueError()
        response=json.loads(raw)
        if not isinstance(response,dict) or set(response)!={'result'}:raise ValueError()
        return response['result']
    except (OSError,ValueError):
        raise McpFault(-32603,'The original Studio tool result is unconfirmed. Inspect the original receipt before continuing.') from None


def main():
    # The native runtime receives this one immutable script and frozen JSON.
    # It cannot select an executable, input file, socket, endpoint or CLI flags.
    if len(sys.argv)!=1:raise SystemExit(1)
    try:
        path=Path('/bridge/tools.json')
        if path.stat().st_size>MAX_REQUEST:raise ValueError()
        server=StudioMcp(json.loads(path.read_bytes()),broker)
        while True:
            raw=sys.stdin.buffer.readline(MAX_REQUEST+1)
            if not raw:return
            if not raw.endswith(b'\n') or len(raw)>MAX_REQUEST:raise ValueError()
            request=None
            try:
                request=json.loads(raw);result=server.handle(request)
                if result is None:continue
                response={'jsonrpc':'2.0','id':request['id'],'result':result}
            except (ValueError,McpFault) as fault:
                response={'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,
                    'error':{'code':fault.code if isinstance(fault,McpFault) else -32700,
                        'message':str(fault) if isinstance(fault,McpFault) else 'Invalid bounded MCP JSON.'}}
            output=json.dumps(response,separators=(',',':'),ensure_ascii=False).encode()+b'\n'
            if len(output)>MAX_RESULT:raise ValueError()
            sys.stdout.buffer.write(output);sys.stdout.buffer.flush()
    except (OSError,ValueError,TypeError):raise SystemExit(1) from None


if __name__=='__main__':main()
