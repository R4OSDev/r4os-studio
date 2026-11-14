import { useContext, useEffect, useState } from 'react';
import type { ConnectionLimits } from '../../../../shared/connection-limits';
import type { ClaudeSubscriptionLimits } from '../../../../shared/claude-subscription';
import { ProviderUsageSource } from '../llm-providers/useProviders';
import { claudeWindows, connectionWindows, usageWindows } from '../llm-providers/limit-windows';
import type { LimitWindow } from '../llm-providers/limit-windows';
import { dateTime } from '../llm-providers/usage-format';
import { gaugePercent, SessionGauge } from './SessionGauge';
import { sessionPath, useSessionApi } from './api';

function used(window:LimitWindow) {
  return window.remainingPercent===null?null:(100-window.remainingPercent)/100;
}

export function UsageIndicator({projectId,sessionId,providerId,model,modelName,nativeClaude}:{
  projectId:string;sessionId:string;providerId:string;model:string;modelName?:string;nativeClaude:boolean;
}) {
  const api=useContext(ProviderUsageSource);
  const observe=api?.request;
  const {request}=useSessionApi();
  const account=api?.nativeProviders.find(p=>p.id===providerId && p.status==='connected' && p.account);
  const connection=api?.providers.find(p=>p.id===providerId && p.type==='api' && p.enabled && p.keyConfigured);
  const native=nativeClaude?api?.providers.find(p=>p.id===providerId && p.type==='claude-subscription' && p.status==='connected'):undefined;
  const accountPath=account && `/${providerId}/usage`;
  const connectionPath=connection?.type==='api' ? (connection.kind==='zai-coding-plan'
    ? `/api-connections/${providerId}/subscription-limits` : ['claude-plan','openrouter'].includes(connection.kind)
      ? `/api-connections/${providerId}/limits` : undefined) : undefined;
  const path=connectionPath || accountPath;
  const scope=connection?.type==='api'?connection.revision+':'+connection.credentialRevision:account?.account?.scope;
  const nativeKey=native?.type==='claude-subscription'?providerId+':'+sessionId+':'+native.revision:null;
  const [nativeSample,setNativeSample]=useState<{key:string;value:ClaudeSubscriptionLimits|null;stale:boolean}>();
  const [checkedNow,setCheckedNow]=useState(()=>Date.now());
  useEffect(()=>{
    if(!path&&!nativeKey)return;
    const tick=()=>setCheckedNow(Date.now());
    const timer=window.setInterval(tick,30_000);
    window.addEventListener('focus',tick);
    return()=>{window.clearInterval(timer);window.removeEventListener('focus',tick);};
  },[path,nativeKey]);
  useEffect(()=>{
    if (!path || !observe) return;
    const refresh=()=>{if(!document.hidden)void observe(path).catch(()=>undefined);};
    refresh();
    const timer=window.setInterval(refresh,60_000);
    window.addEventListener('focus',refresh);
    return()=>{window.clearInterval(timer);window.removeEventListener('focus',refresh);};
  },[observe,path,scope]);
  useEffect(()=>{
    if(!nativeKey)return;
    const controller=new AbortController();
    const refresh=()=>{
      if(document.hidden || controller.signal.aborted)return;
      void request<{limits:ClaudeSubscriptionLimits|null}>(sessionPath(projectId,sessionId)+'/claude-limits',
        '', 'GET', undefined, controller.signal).then(({limits})=>{
        if(!controller.signal.aborted)setNativeSample({key:nativeKey,value:limits,stale:false});
      }).catch(()=>{
        if(!controller.signal.aborted)setNativeSample(previous=>previous?.key===nativeKey?{...previous,stale:true}:previous);
      });
    };
    refresh();
    const timer=window.setInterval(refresh,60_000);
    window.addEventListener('focus',refresh);
    return()=>{controller.abort();window.clearInterval(timer);window.removeEventListener('focus',refresh);};
  },[nativeKey,request,projectId,sessionId]);

  const matchedNative=nativeSample?.key===nativeKey?nativeSample?.value:null;
  const observation=accountPath?api?.usageByProvider[providerId]:null;
  const sample=connection?.type==='api'?api?.connectionLimits[providerId]:null;
  const matched:ConnectionLimits|null=sample && connection?.type==='api'
    && sample.configRevision===connection.revision && sample.credentialRevision===connection.credentialRevision?sample:null;
  const selection={id:model,name:modelName};
  const windows=(matchedNative?claudeWindows(matchedNative.windows,'current',selection)
    : matched?connectionWindows(matched,selection):usageWindows(observation??null,model))
    .filter(window=>!window.unlimited)
    .sort((left,right)=>(left.durationMinutes??Infinity)-(right.durationMinutes??Infinity)
      || (used(right)??-1)-(used(left)??-1));
  if(!windows.length)return null;
  const checked=matchedNative?.receivedAt??matched?.checkedAt??observation?.usage?.fetchedAt??null;
  const stale=(matchedNative?nativeSample?.stale:matched?matched.state!=='current':observation?.state==='stale')
    || !!checked && checkedNow-Date.parse(checked)>120000
    || windows.some(window=>window.resetsAt && Date.parse(window.resetsAt)<=checkedNow);
  const count=used(windows[0]);
  return <SessionGauge label="Usage" ratio={count} details={<>
    <ul>{windows.map(window=>{
      const value=used(window);
      return <li key={window.id}><strong>{window.label}</strong> · {window.scope} · {value===null?'Not reported':gaugePercent.format(value)+' used'}
        {window.resetsAt && <small>Reset {dateTime(window.resetsAt)}</small>}</li>;
    })}</ul>
    {checked&&Number.isFinite(Date.parse(checked))&&<small>Observed {dateTime(checked)}</small>}
    {stale&&<small>Last known usage</small>}
  </>}/>;
}
