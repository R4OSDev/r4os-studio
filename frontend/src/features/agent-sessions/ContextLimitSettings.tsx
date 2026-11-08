import type { ContextLimitDefaults, ContextLimitPreference } from '../../../../shared/agent-sessions';
import './context-limit.css';

export function ContextLimitSettings({mode,text,defaults,modelWindow,changeMode,changeText}: {
  mode:ContextLimitPreference['mode']; text:string; defaults?:ContextLimitDefaults; modelWindow?:number|null;
  changeMode:(mode:ContextLimitPreference['mode'])=>void; changeText:(text:string)=>void;
}) {
  const enabled=mode==='on'||mode==='global'&&defaults?.enabled;
  return <div className="session-context-limit">
    <fieldset className="context-limit-modes"><legend>Input limit</legend>
      {([['off','Off'],['global','Global default'],['on','On']] as const).map(([value,label])=><label key={value}>
        <input type="radio" name="context-limit-mode" value={value} checked={mode===value} onChange={()=>changeMode(value)}/><span>{label}{value==='global'&&<small>Default</small>}</span>
      </label>)}
    </fieldset>
    <p>Off uses model limits. Global default follows the global switch. On enables the input limit for this session.</p>
    {defaults?<p>Global limit: {defaults.enabled?'On':'Off'} · {defaults.budgetTokens.toLocaleString('en-US')} tokens.</p>:<p role="status">Global context settings are unavailable. Reload session options to confirm the inherited value.</p>}
    {enabled&&<>
      <label htmlFor="session-context-budget">Session input limit (tokens, optional)</label>
      <input id="session-context-budget" type="text" inputMode="numeric" value={text} placeholder={defaults?String(defaults.budgetTokens):'Use global value'} aria-describedby="session-context-budget-help" onChange={event=>changeText(event.target.value)}/>
      <p id="session-context-budget-help">Leave empty to use the saved global value. A custom value applies only to this session. Whole number from 1 to {(defaults?.maxBudgetTokens??10000000).toLocaleString('en-US')}.</p>
    </>}
    <p>{enabled?'The limit covers the entire provider input, including instructions, tools, conversation, summaries and media.':'The additional input limit is off. Any saved session value is kept and ignored.'} Lower model limits always apply{modelWindow?`; the selected model’s context window is ${modelWindow.toLocaleString('en-US')} tokens`:''}. Changes apply from the next accepted run.</p>
  </div>;
}
