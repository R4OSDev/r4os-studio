"""Frozen Goal facet of one ordinary run; browser controls never shorten its loop."""
import copy
import json
import time
from session_store import encode
import goal_keepalive as control


class RunGoal:
    def __init__(self,worker):
        self.w=worker;self.original=copy.deepcopy(worker.config['goalKeepalive'])
        self.execution=self.original['playRequestId'];self.dormant=False;self.charged=set();self.goal=copy.deepcopy(self.original['goal'])
    @property
    def active(self):return True  # Run authority is frozen, independently of future keepalive controls.
    def current(self):return copy.deepcopy(self.goal)
    def instructions(self):return ''  # Shared frozen instruction composition covers every runtime.
    async def start(self):
        if self.w.config['engine'].get('kind')=='studio':
            self.w.thread_id=self.w.store.row(self.w.session_id)['thread_id'] or self.w.session_id
            with self.w.store.db:self.w.store.db.execute('UPDATE sessions SET thread_id=? WHERE id=? AND thread_id IS NULL',(self.w.thread_id,self.w.session_id))
    async def boundary(self,allow_play=True):pass
    async def close(self):
        if self.w.config['engine'].get('kind')!='studio':self.missing_usage('native-'+self.w.run_id)
    def missing_usage(self,request_id):self.record_usage(request_id,None)
    def observe(self,result,request_id):
        from studio_goal import spending
        self.record_usage(request_id,spending(result.get('usage'),self.w.config.get('apiProvider',{}).get('protocol')))
    def record_usage(self,request_id,total):
        if request_id in self.charged:return
        self.charged.add(request_id);store=self.w.store;store.db.execute('BEGIN IMMEDIATE')
        try:
            value=control.row(store,self.w.session_id)
            if value and value['generation']==self.original['generation'] and value['goal']['goalId']==self.goal['goalId']:
                count=value['goal'].get('tokensUsed');value['goal']['tokensUsed']=count+total if type(count) is int and type(total) is int and count+total<=2**53-1 else None
                value['goal']['updatedAt']=int(time.time());control.write(store,self.w.session_id,value)
            store.db.commit()
        finally:
            if store.db.in_transaction:store.db.rollback()
    async def pause(self,status='paused',reason=None,**kwargs):
        value=control.row(self.w.store,self.w.session_id)
        if value and value['generation']==self.original['generation'] and value['goal']['goalId']==self.goal['goalId']:
            control.block(self.w.store,self.w.session_id,reason or 'The original Goal run reached a limit.',status=status,expected=self.original['generation'])
    async def tool(self,name,arguments):
        if name=='get_goal':return {'success':True,'output':encode({'goal':self.current(),'runId':self.w.run_id,'keepaliveChangesApplyAfterRun':True})}
        store=self.w.store
        for rid in arguments.get('receiptIds',[]):
            rows=store.db.execute('SELECT t.state,t.result FROM tools t JOIN runs r ON r.id=t.run_id WHERE r.session_id=? AND t.call_id=?',(self.w.session_id,rid)).fetchall()
            if len(rows)!=1 or rows[0]['state']!='completed' or not rows[0]['result'] or not json.loads(rows[0]['result']).get('success'):
                return {'success':False,'error':'unconfirmedEvidence','output':'Completion needs a confirmed original receipt.'}
        self.goal.update(status=arguments['status'],updatedAt=int(time.time()))
        store.db.execute('BEGIN IMMEDIATE')
        try:
            value=control.row(store,self.w.session_id);applies=bool(value and value['generation']==self.original['generation'] and value['goal']['goalId']==self.goal['goalId'])
            if applies:
                control.checkpoint(value,store=store,sid=self.w.session_id)
                value.update(active=False,revision=value['revision']+1,reason=arguments['reason']);value['goal'].update(status=arguments['status'],updatedAt=int(time.time()))
                control.write(store,self.w.session_id,value)
                from goal_keepalive_clock import record
                record(store,self.w.session_id,value)
                control.publish(store,self.w.session_id)
            store.db.commit()
        finally:
            if store.db.in_transaction:store.db.rollback()
        return {'success':True,'output':encode({'goal':self.current(),'appliedToCurrentKeepalive':applies,'runContinuesNormally':True})}
