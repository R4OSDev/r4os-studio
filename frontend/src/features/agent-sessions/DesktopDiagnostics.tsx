import type {DesktopDiagnostics as Diagnosis} from '../../../../shared/project-development';
const fact=(value:unknown)=>value===undefined||value===null?'Unconfirmed':String(value);
export function DesktopDiagnostics({value}:{value:Diagnosis}) {
  const launch=value.launch,previous=value.window.earlier,current=value.window.current;
  return <div className="development-execution-evidence" aria-label="Desktop diagnostics">
    <p>DESKRUN: {fact(launch.error)} ({fact(launch.errorlevel)}) · Phase {fact(launch.phase)} · Terminal {fact(launch.terminal)}</p>
    <p>Launch: {launch.state} · Protocol {fact(launch.adapter)} {fact(launch.contract)} · {value.source}</p>
    {launch.statusError&&<p>Status read: {launch.statusError} ({fact(launch.statusErrorlevel)}) · Earlier receipt retained.</p>}
    <p>Process: {value.process.confirmed?`${value.process.instanceId} · Generation ${value.process.generation}`:'Unconfirmed'}</p>
    <p>Earlier native window: {fact(previous.window)} · Content counter {fact(previous.content)} · Content {previous.contentConfirmed?'confirmed':'unconfirmed'}</p>
    <p>Current window: {fact(current.windowId)} · Visible {fact(current.windowVisible)} · Focused {fact(current.windowFocused)}</p>
    <p>App exit: {value.appExit.confirmed?value.appExit.code:'Unconfirmed'} · {value.appExit.source}</p>
    {(value.appExit.stopReason||value.appExit.exitReason!==undefined)&&<p>Native stop reason: {fact(value.appExit.stopReason)} · Native exit reason: {fact(value.appExit.exitReason)}</p>}
    <p>Process end: {value.processEndConfirmed?'Confirmed':'Unconfirmed'} · Cleanup: {value.cleanupConfirmed?'Confirmed':'Unconfirmed'} · Checks: {value.checkState}</p>
    <p>Launcher exit and terminal describe the request. Native app exit values do not establish a POSIX signal or crash cause. Process existence does not prove content readiness; the cause remains unresolved.</p>
  </div>;
}
