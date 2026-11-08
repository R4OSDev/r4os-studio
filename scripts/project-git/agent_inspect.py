#!/usr/bin/env python3
"""Own active-run read sidecar; no publication or credential access."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
from common import ProjectFault, document, project_id
from agent import AgentLease, process
from agent_push import rpc


def main():
    os.umask(0o077)
    if len(sys.argv)!=6:raise ProjectFault('Invalid own Git read invocation.',400)
    projects=Path(sys.argv[1]).absolute();identity,session,run=map(project_id,sys.argv[2:5]);descriptor=int(sys.argv[5])
    config=document(Path('/etc/r4os-studio-git/config.json'))
    if Path(config['projects']) != projects:raise ProjectFault('Git storage binding changed.',403)
    raw=sys.stdin.buffer.read(131073)
    if len(raw)>131072:raise ProjectFault('Git read arguments exceed128KiB.',400)
    data=json.loads(raw)
    if not isinstance(data,dict) or set(data)!={'callId','input'}:raise ProjectFault('Invalid Git read arguments.',400)
    with closing(sqlite3.connect((projects/identity/'Sessions/Sessions.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT r.config FROM runs r JOIN sessions s ON s.id=r.session_id WHERE r.id=? AND s.id=? AND s.project_id=?',(run,session,identity)).fetchone()
    if not row:raise ProjectFault('The own original Git read run is unavailable.',403)
    frozen=json.loads(row[0]);parent=os.getppid()
    owner={'sessionId':session,'runId':run,'workerPid':parent,'workerBirth':process(parent)[1],
        'revision':frozen['revision'],'callId':data['callId']}
    AgentLease(config,identity,owner,descriptor,read_only=True).verify()
    capabilities=rpc({'operation':'capabilities'})
    if capabilities.get('agentReadVersion')!=1:raise ProjectFault('Git inspection requires the current idle-adopted coordinator.',503)
    result=rpc({'operation':'agent_inspect','projectId':identity,'agent':owner,'input':data['input']},descriptor,timeout=120)
    encoded=json.dumps({'result':result},ensure_ascii=False)
    if len(encoded.encode())>12288:raise ProjectFault('The bounded Git read page exceeded12KiB.',503)
    print(encoded)


if __name__=='__main__':
    try:main()
    except ProjectFault as error:print(json.dumps({'error':str(error),'code':error.code}));sys.exit(1)
    except Exception:print(json.dumps({'error':'The own Git read is unavailable. No commit, pull or push was started.','code':503}));sys.exit(1)
