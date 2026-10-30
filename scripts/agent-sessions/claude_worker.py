"""Native Claude worker; reuses Studio effects without inventing Codex RPCs."""
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time

from worker import Worker,reconcile_items
from claude_history import ClaudeHistory
from claude_tool_broker import ClaudeToolBroker
from run_store import get_run,transition,item,event,request_text
from session_store import encode
from owner import open_lock
from profile import tools_for
from store import ProjectFault


class ClaudeWorker(Worker):
    def __init__(self,manifest):
        super().__init__(manifest)
        if self.config['engine'].get('kind')!='claude-code':raise ValueError('Wrong native worker engine.')
        self.native=None;self.broker=None;self.reader_task=None;self.ready=asyncio.Event();self.closed=asyncio.Event()
        self.native_result=None;self.native_receipt=None;self.sent=False;self.close_requested=False
        self.native_error_code=None;self.native_retry_observed=False
        self.transport_ready=asyncio.Event();self.initialized=False
        self.active_provider=None;self.blocks={};self.snapshots=set();self.block_sequence=0
        self.socket_root=Path('/run/r4os-studio-agents')/('claude-'+self.run_id)
        self.credential_lease=None;self.credential_worker=None
        self.admission_started_at=None
        self.admission_denial=None
        self.quota_blocked=None;self.quota_guard_task=None;self.quota_authorized_through=None
        from claude_input_usage import InputUsage
        self.input_usage=InputUsage(self)
        from claude_messages import queued
        self.queued_input=queued(self);self.input_receipt=asyncio.Event()
        self.claude_goal=None
        self.live_control=None
        if self.config.get('claudeGoalExecution'):
            from claude_goal_worker import ClaudeGoalRuntime
            self.claude_goal=ClaudeGoalRuntime(self)
        from claude_retry import ClaudeRetry
        self.claude_retry=ClaudeRetry(self)

    async def admit_native(self,binding,account,usage,retry=None):
        from claude_admission import admit
        result=await admit(self,binding,account,usage)
        if self.claude_goal and retry is None:
            try:self.claude_goal.admitted(result)
            except ProjectFault as error:result={'allowed':False,'reasonCode':'goal_control','reason':str(error)}
        if result.get('allowed') is not True:self.admission_denial=result
        return result

    async def current(self,binding):
        row=get_run(self.store,self.run_id)
        from claude_run_leases import ClaudeRunLeases
        valid=(not self.stopping and bool(row['busy']) and row['state']!='stopping' and binding==self.broker.binding
            and self.credential_lease is not None and ClaudeRunLeases(self.manifest['providers']).current_lease(self.credential_lease,self.credential_worker)
            and self.store.get(self.session_id)['engine'].get('claude')==self.config['engine'].get('claude'))
        if valid and self.sent:
            from claude_quota_store import QuotaStore
            saved=QuotaStore(self.manifest['providers']).read(self.config['providerId'])
            from claude_quota_guard import block,effective_hold
            hold=effective_hold(self,saved)
            if hold:
                block(self,hold);return False
        return valid

    async def mcp_output(self,result,image_data=None):
        content=[{'type':'text','text':encode(result)}]
        if result.get('image') and self.config.get('claudeModel',{}).get('imageInput')!='supported':
            content.append({'type':'text','text':'The original screenshot was captured and retained, but image delivery is unavailable for this model. This result does not confirm visual inspection.'})
        if result.get('image') and self.config.get('claudeModel',{}).get('imageInput')=='supported':
            image=result['image']
            if not self.config['permissions'].get('studio.capture_vm'):
                return {'content':[{'type':'text','text':'Image inspection is disabled in the original Studio run.'}],'isError':True}
            data=image_data if image_data is not None else await self.development.request('evidence',id=image['jobId'],evidenceId=image['id'])
            if data['metadata']!=image or image.get('projectId')!=self.manifest.get('projectId') or image.get('kind')!='screenshot':
                raise ValueError('The original screenshot binding changed.')
            content.append({'type':'image','mimeType':'image/png','data':data['base64']})
        return {'content':content,'isError':not result['success']}

    async def effect(self,name,arguments,call_id):
        admission_error=None
        if (self.queued_input or self.claude_goal or self.config.get('claudeInput')) and not self.input_receipt.is_set():
            try:await asyncio.wait_for(self.input_receipt.wait(),2)
            except asyncio.TimeoutError:
                admission_error={'success':False,'error':'inputUnconfirmed',
                    'output':'The original Claude input ID is not confirmed. No Studio tool was executed.'}
        if name=='studio_report_goal':
            if not self.claude_goal or not self.claude_goal.begun:
                return await self.mcp_output({'success':False,'error':'unavailable','output':'No original Studio GOAL input is active. This ordinary request grants no GOAL authority.'})
            return await self.claude_goal.report(arguments,call_id,admission_error)
        async def output(result,image_data=None):
            # A resumed native call can reuse an original receipt from an older
            # run. Publish its confirmed UI result without executing it again.
            previous=self.items.get(call_id)
            if previous is None or previous.get('status')=='pending':
                from terminal import bounded_text
                text,clipped=bounded_text(str(result.get('output','')),180000)
                value={'id':call_id,'runId':self.run_id,'type':'tool','tool':name.replace('studio_','studio.',1),
                    'arguments':arguments,'status':'completed' if result['success'] else {'disabled':'denied','unknown':'unknown','interrupted':'interrupted'}.get(result.get('error'),'failed'),
                    'output':text,'error':result.get('error'),'truncated':bool(clipped or result.get('truncated') or result.get('outputTruncated'))}
                for key in ('remote','roadmap','development','developmentStop','github','image','exitCode','signal','reason','nextLine','nextOffset','totalLines','lineTruncated','skippedFiles','reasonCode','partialChangesPossible','files','skill','generatedAsset'):
                    if key in result:value[key]=result[key]
                self.items[call_id]=value;item(self.store,self.session_id,self.run_id,value)
            return await self.mcp_output(result,image_data)
        return await self.bound_tool(name,arguments,call_id,output,admission_error=admission_error)

    async def command(self,operation,**fields):
        if not self.native or self.native.returncode is not None:raise RuntimeError('The original native process is unavailable.')
        self.native.stdin.write((encode({'operation':operation,**fields})+'\n').encode());await self.native.stdin.drain()

    def text_item(self,provider,index):
        key=(provider,index)
        if key not in self.blocks:
            ident='claude-text-'+hashlib.sha256((provider+':'+str(index)).encode()).hexdigest()[:40]
            self.blocks[key]={'id':ident,'runId':self.run_id,'type':'assistant','text':'','status':'running',
                'nativeOrigin':{'nativeSessionId':self.config['engine']['claude']['nativeSessionId'],'providerMessageId':provider,'nativeTurnId':None}}
            item(self.store,self.session_id,self.run_id,self.blocks[key])
        return self.blocks[key]

    def publish_text(self,value,text,complete=False):
        if not isinstance(text,str) or len(text.encode())>196608:raise ValueError('The native message exceeds the Studio display bound.')
        value.update(text=text,status='completed' if complete else 'running');item(self.store,self.session_id,self.run_id,value)

    async def observe(self,frame):
        native=frame['native'];kind=native['type'];identity=frame['identity']
        if identity.get('nativeSessionId') not in (None,self.config['engine']['claude']['nativeSessionId']):raise ValueError('Native session changed.')
        retry_input=await self.claude_retry.frame(frame)
        from claude_messages import acknowledge
        if not retry_input:
            if not (self.claude_goal and self.claude_goal.live and self.claude_goal.begun):acknowledge(self,frame)
            if self.claude_goal:self.claude_goal.acknowledge(frame)
        self.input_usage.notify(native)
        if kind=='stream_event':
            stream=native['event'];event_type=stream.get('type');index=stream.get('index')
            if event_type=='message_start':self.active_provider=stream.get('message',{}).get('id')
            elif event_type=='content_block_start' and stream.get('content_block',{}).get('type')=='text':
                if not self.active_provider or type(index) is not int:raise ValueError('Unbound native text block.')
                self.text_item(self.active_provider,index)
            elif event_type=='content_block_delta' and stream.get('delta',{}).get('type')=='text_delta':
                if not self.active_provider or type(index) is not int:raise ValueError('Unbound native text delta.')
                value=self.text_item(self.active_provider,index);delta=stream['delta']['text']
                if not isinstance(delta,str) or len((value['text']+delta).encode())>196608:raise ValueError('Native text exceeds its bound.')
                value['text']+=delta
                self.store.db.execute('INSERT INTO items VALUES (?,?,?,?) ON CONFLICT(session_id,run_id,item_id) DO UPDATE SET payload=excluded.payload',
                    (self.session_id,self.run_id,value['id'],encode(value)))
                event(self.store,self.session_id,self.run_id,'delta',{'itemId':value['id'],'text':delta})
        elif kind=='assistant':
            if native.get('error'):
                self.native_error_code=native['error']
                self.error=native.get('error_message') or 'Claude could not complete this original request.'
                if self.broker:
                    if self.claude_retry.enabled:self.broker.suspend_admission()
                    else:self.broker.stop_admission()
                return  # Never render raw native error text or synthetic tool blocks.
            if native.get('uuid') in self.snapshots:return
            self.snapshots.add(native.get('uuid'));message=native.get('message') or {};provider=message.get('id')
            if not isinstance(provider,str):raise ValueError('Unbound native provider message.')
            matched=set()
            for part in message.get('content',[]):
                if part['type']=='text':
                    available=[value for (pid,_),value in self.blocks.items() if pid==provider and value['id'] not in matched]
                    candidates=[value for value in available if value['status']=='running']
                    exact=[value for value in candidates+available if value['text']==part['text']]
                    if exact:value=exact[0]
                    elif candidates:value=candidates[0]
                    else:
                        self.block_sequence+=1;value=self.text_item(provider,100000+self.block_sequence)
                    matched.add(value['id'])
                    self.publish_text(value,part['text'],True)
                elif part['type']=='tool_use':
                    tool=part['name']
                    if not isinstance(tool,str) or not tool.startswith('mcp__studio__'):raise ValueError('Unbound native tool name.')
                    call=part['id'];value=self.items.get(call)
                    if value is None:
                        value={'id':call,'runId':self.run_id,'type':'tool','tool':'studio.'+tool[len('mcp__studio__'):],
                            'arguments':part['input'],'status':'pending'}
                        self.items[call]=value;item(self.store,self.session_id,self.run_id,value)
        elif kind=='system' and native.get('subtype')=='api_retry':
            from claude_provider_errors import retry_notice
            self.native_retry_observed=True
            notice=retry_notice(native.get('nativeRetry'))
            event(self.store,self.session_id,self.run_id,'notice',
                {'text':notice['text'],'nativeProviderRetry':{**{k:v for k,v in notice.items() if k!='text'},
                    'nativeSessionId':self.config['engine']['claude']['nativeSessionId'],
                    'nativeInputRequestIds':identity.get('nativeInputRequestIds',[]),'inputBindingQualified':False}})
        elif kind=='system' and native.get('subtype')=='compact_boundary':
            event(self.store,self.session_id,self.run_id,'notice',{'text':'Claude compacted its original native conversation.'})
        elif kind=='rate_limit_event':
            from claude_limits_policy import event_sample
            try:observation=event_sample(native.get('rate_limit_info'))
            except (ValueError,OverflowError,OSError):
                observation={'schema':1,'source':'claude-code-2.1.312/sdk-0.3.312/rate_limit_event',
                    'receivedAt':__import__('session_store').now(),'status':'unavailable','scope':None,
                    'usedPercent':None,'resetsAt':None,'overageEnabled':None,'usingOverage':False}
            observation.update(studioSessionId=self.session_id,providerId=self.config['providerId'],runId=self.run_id)
            observation['accountIdentity']=self.config.get('claudeProvider',{}).get('accountIdentity')
            from claude_quota_store import QuotaStore
            saved=QuotaStore(self.manifest['providers']).record(self.config['providerId'],observation=observation) if observation['accountIdentity'] else None
            event(self.store,self.session_id,self.run_id,'claudeQuota',observation)
            if saved and saved['hold']:
                from claude_quota_guard import block
                block(self,saved['hold'])
        elif kind=='result':
            self.native_result=native
            from claude_usage_receipts import record as usage_receipt
            usage_receipt(self,native)
            if native.get('is_error') is True and native.get('providerError'):
                from claude_provider_errors import describe
                failure=describe(native['providerError'],self.native_error_code,self.native_retry_observed)
                if not self.stopping and not self.admission_denial and not self.quota_blocked and not self.uncertain_effect:
                    self.error=failure['text']
                event(self.store,self.session_id,self.run_id,'notice',
                    {'text':failure['text'],'providerError':{**{k:v for k,v in failure.items() if k!='text'},
                        'nativeResultId':native['uuid'],'nativeInputRequestIds':identity.get('nativeInputRequestIds',[])}})
            if await self.claude_retry.result(frame):return
            if self.claude_goal and await self.claude_goal.result(native,identity):return
            if self.live_control:self.live_control.close_intent()
            if self.stopping:
                if self.outcome not in ('completed','failed'):self.outcome='unknown' if self.uncertain_effect else 'interrupted'
            else:
                self.outcome=('unknown' if self.claude_retry.uncertain_start else
                    'completed' if native.get('subtype')=='success' and not native.get('is_error') else 'failed')
                if self.outcome=='failed':self.error=self.error or 'The original native Claude execution ended with an error.'
            self.done.set()

    async def read_native(self):
        try:
            while raw:=await self.native.stdout.readline():
                if len(raw)>524288 or not raw.endswith(b'\n'):raise ValueError('Native worker output exceeds its bound.')
                value=json.loads(raw);kind=value.get('event')
                if kind=='native':await self.observe(value)
                elif kind=='transport_ready':
                    if value.get('nativeSessionId')!=self.config['engine']['claude']['nativeSessionId']:raise ValueError('Native transport session changed.')
                    self.transport_ready.set()
                elif kind=='ready':self.initialized=True;self.ready.set()
                elif kind=='submitted':
                    if value.get('requestId')!=self.row['request_id']:raise ValueError('Original native request changed.')
                    if self.claude_goal and self.claude_goal.begun:
                        self.claude_goal.submitted(value)
                        if not self.claude_retry.holding:self.native_result=None
                    self.sent=True;transition(self.store,self.run_id,'running')
                    if self.live_control and not self.claude_goal:
                        from claude_live_store import open_source
                        open_source(self)
                elif kind in ('goal_armed','goal_arm_refused'):
                    if not self.live_control:raise ValueError('Unexpected native live Goal receipt.')
                    self.live_control.native_arm(value)
                elif kind=='retry_submitted':
                    self.claude_retry.submitted(value)
                    self.sent=True;transition(self.store,self.run_id,'running')
                elif kind=='unconfirmed':
                    if value.get('requestId')!=self.row['request_id']:raise ValueError('Original native unconfirmed request changed.')
                    if await self.claude_retry.unconfirmed(value):continue
                    if self.claude_goal:self.claude_goal.unconfirmed(value)
                    self.sent=self.sent or value.get('promptSubmitted') is True
                    self.error=(self.admission_denial or {}).get('reason') or value['message']
                    known_no_input=self.claude_goal and self.claude_goal.unsubmitted_after_result()
                    self.outcome=('interrupted' if self.stopping else 'failed') if known_no_input or not self.sent else 'unknown'
                    self.done.set();self.ready.set()
                elif kind=='closed':
                    if value.get('nativeSessionId')!=self.config['engine']['claude']['nativeSessionId']:raise ValueError('Native closure session changed.')
                    if value.get('studioRequestId')!=self.row['request_id']:raise ValueError('Original native closure request changed.')
                    self.native_receipt=value;self.closed.set()
            if not self.closed.is_set():raise ValueError('Original native worker closed without its final receipt.')
        except Exception:
            self.error=self.error or 'The original native Claude stream is unconfirmed. It was not replayed.';self.outcome='unknown';self.done.set()
        finally:self.ready.set();self.transport_ready.set()

    async def _stop(self):
        self.stopping=True
        if self.broker:self.broker.stop_admission()
        if self.claude_goal:
            try:self.claude_goal.stop()
            except Exception:
                self.uncertain_effect=True
                self.error=self.error or 'The original bounded GOAL ledger is unconfirmed. Native Stop still closes admission.'
        try:await self.claude_retry.cancel()
        except Exception:
            self.claude_retry.uncertain_start=True
            self.error=self.error or 'The original retry ledger is unconfirmed. Native Stop still closes admission.'
        if self.native and self.native.returncode is None:
            try:await self.command('interrupt')
            except (OSError,RuntimeError):self.uncertain_effect=True
        await super()._stop()

    async def finish_native(self):
        if not self.native:return False
        if self.broker:self.broker.stop_admission()
        if self.native.returncode is None and not self.close_requested:
            self.close_requested=True
            try:await self.command('close')
            except (OSError,RuntimeError):pass
        try:
            await asyncio.wait_for(self.native.wait(),18)
            if self.reader_task:await asyncio.wait_for(self.reader_task,3)
        except asyncio.TimeoutError:
            try:os.killpg(self.native.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            await self.native.wait();return False
        return (self.native.returncode==0 and self.native_receipt is not None and self.native_receipt.get('originalStreamConfirmed') is True)

    async def run(self):
        if not self.row['busy']:return
        loop=asyncio.get_running_loop()
        for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,lambda:asyncio.create_task(self.stop()))
        history=ClaudeHistory(self.store,self.session_id);prepared=None
        try:
            if self.row['state']=='stopping':self.outcome='interrupted';return
            if any(self.config.get(key) for key in ('goalExecution','nativeGoalPreparation','apiProvider','nativeImageGeneration','webSearchEnabled','fastMode')):
                raise ProjectFault('This native Claude input/lifecycle capability has not been qualified.',409)
            if self.config.get('attachments'):
                from claude_inputs import prepared_input
                if prepared_input(self.store,self.session_id,self.run_id,self.config) is None:
                    raise ProjectFault('The original Claude attachments have no qualified native input contract.',409)
            self.lease=open_lock(self.store.projects,self.store.owner_type,self.store.owner_id);fcntl.flock(self.lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
            from claude_run_leases import ClaudeRunLeases
            selected=self.config.get('claudeProvider');original=history.get();frozen=original['runtime']
            if (not isinstance(selected,dict) or set(selected)!={'providerId','providerRevision','runtimeProfileId','accountIdentity'}
                or selected['providerId']!=self.config['providerId'] or selected['runtimeProfileId']!=frozen['runtimeProfileId']):
                raise ProjectFault('The original native Claude provider snapshot is unavailable. No model was started.',409)
            if not original['accountIdentity'] or original['accountIdentity']!=selected['accountIdentity']:
                raise ProjectFault('The native account behind this Claude provider changed. Preserve this conversation and use a new session for the new account.',409)
            credential={**selected,'studioSessionId':self.session_id,'ownerType':self.store.owner_type,'ownerId':self.store.owner_id,
                'runId':self.run_id,'requestId':self.row['request_id'],'nativeSessionId':frozen['nativeSessionId']}
            self.credential_worker={'release':self.manifest['release'],'pid':os.getpid(),'birth':__import__('lease').birth(os.getpid())}
            ClaudeRunLeases(self.manifest['providers']).claim(credential,self.credential_worker);self.credential_lease=credential
            if self.store.owner_type=='project':await self.build_snapshots.start()
            transition(self.store,self.run_id,'starting',worker={'release':self.manifest['release'],'pid':os.getpid(),'birth':__import__('lease').birth(os.getpid())})
            if self.claude_goal:
                self.claude_goal.start()
                from claude_goal_control import ClaudeGoalControl
                self.claude_goal.control=ClaudeGoalControl(self.claude_goal);await self.claude_goal.control.start()
            elif self.config.get('claudeGoalPreparation') is True:
                from claude_live_control import ClaudeLiveGoalControl
                self.live_control=ClaudeLiveGoalControl(self);await self.live_control.start()
            prepared=history.prepare(self.run_id);frozen=prepared['runtime']
            binding={'providerId':self.config['providerId'],'studioSessionId':self.session_id,'nativeSessionId':frozen['nativeSessionId'],
                'runId':self.run_id,'requestId':self.row['request_id'],'ownerType':self.store.owner_type,'ownerId':self.store.owner_id,
                'model':self.config['model'],'toolProfile':self.config['engine']['profile']}
            tool_names=tools_for(self.config['engine']['profile'])+(('report_goal',) if self.claude_goal or self.live_control else ())
            self.broker=ClaudeToolBroker(self.socket_root,binding,tool_names,self.current,self.effect,
                admit=self.admit_native,retry=self.claude_retry)
            await self.broker.start()
            from claude_namespace import prepare
            args=prepare(self,history,prepared,self.broker)
            self.native=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,env={'PATH':'/usr/bin'},start_new_session=True,limit=524289,umask=0o077)
            self.reader_task=asyncio.create_task(self.read_native());await asyncio.wait_for(self.transport_ready.wait(),15)
            if self.done.is_set():raise ProjectFault(self.error or 'The original native transport was not confirmed.',409)
            await self.command('initialize')
            await asyncio.wait_for(self.ready.wait(),20)
            if self.done.is_set() or self.stopping:raise ProjectFault('The original native Claude startup was not confirmed.',409)
            self.claude_retry.bind()
            from claude_quota_guard import watch
            self.quota_guard_task=asyncio.create_task(watch(self))
            self.admission_started_at=time.time()
            await self.command('send',text=self.config['claudeGoalExecution']['objective'] if self.claude_goal else request_text(self.store,self.run_id))
            await self.done.wait()
        except Exception as error:
            self.error=self.error or (str(error) if isinstance(error,ProjectFault) else 'The native Claude run could not confirm its original result.')
            self.outcome='unknown' if self.sent else ('interrupted' if self.stopping else 'failed')
        finally:
            if self.quota_guard_task:
                self.quota_guard_task.cancel();await asyncio.gather(self.quota_guard_task,return_exceptions=True)
            confirmed=await self.finish_native()
            try:await self.claude_retry.closed_receipt(confirmed)
            except Exception:
                self.claude_retry.uncertain_start=True;self.outcome='unknown'
            from claude_messages import finalize as finish_input
            finish_input(self)
            if self.credential_lease:
                from claude_run_leases import ClaudeRunLeases
                ClaudeRunLeases(self.manifest['providers']).finish_lease(self.credential_lease,self.credential_worker,confirmed or self.native is None)
            if prepared:
                if confirmed and not self.sent and not self.uncertain_effect and history.unstarted(self.run_id,prepared,self.native_receipt):
                    pass  # No input, no effects and byte-identical history; original UUID remains usable.
                elif (confirmed and self.native_result and self.native_result.get('uuid')==self.native_receipt.get('resultId')
                        and not self.uncertain_effect and not self.claude_retry.uncertain_start):
                    receipt={'nativeSessionId':prepared['runtime']['nativeSessionId'],'nativeResultId':self.native_receipt['resultId'],
                        'studioRequestId':self.row['request_id'],'subtype':self.native_receipt['subtype'],'nativeClosed':True,
                        'historyReadable':self.native_receipt['historyReadable']}
                    try:
                        if history.finish(self.run_id,receipt)['phase']!='ready':self.outcome='unknown'
                    except ProjectFault:history.unconfirmed(self.run_id);self.outcome='unknown'
                else:
                    history.unconfirmed(self.run_id)
                    if self.sent and not (self.stopping and confirmed and not self.uncertain_effect):self.outcome='unknown'
            if self.broker:await self.broker.close()
            if self.claude_goal:
                try:await self.claude_goal.finish(confirmed and history.get()['phase'] in ('ready','allocated'))
                except Exception:self.outcome='unknown';self.error=self.error or 'The original bounded Claude GOAL ledger could not confirm its closure.'
            if self.live_control:await self.live_control.close()
            self.input_usage.finish()
            await self.claude_retry.close()
            await self.cleanup()
            if self.lease:self.lease.close()
            reconcile_items(self.store,self.run_id,self.outcome)
            transition(self.store,self.run_id,self.outcome,self.error)
            self.store.close()
