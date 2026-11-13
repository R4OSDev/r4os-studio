import { useEffect, useState } from 'react';
import type { CSSProperties, FormEvent } from 'react';
import type { VirtualMachine } from '../../../../shared/virtual-machines.js';
import type { VmApi } from './useVms';
import { Icon } from '../../app/Icon';
import { ReleaseSettings } from './ReleaseSettings';
import { VmConsole } from './Console';
import { DevelopmentAccess } from './DevelopmentAccess';
import { ExchangeExplorer } from './ExchangeExplorer';
import { useVmReset, VmResetDialog } from './VmReset';
import './styles.css';
import './exchange.css';

const vmNetworkUnavailable = 'VM network host support is not installed. See the host setup documentation.';

function VmRange({ id, label, value, min, max, step, display, bounds, disabled, change }: {
  id: string; label: string; value: number; min: number; max: number; step: number;
  display: (value: number) => string; bounds?: [string, string]; disabled: boolean; change: (value: number) => void;
}) {
  const selected = display(value);
  const [lower, upper] = bounds ?? [display(min), display(max)];
  return <div className="vm-range">
    <div className="vm-range-label"><label htmlFor={id}>{label}</label><output htmlFor={id}>{selected}</output></div>
    <input id={id} type="range" min={min} max={max} step={step} value={value} aria-valuetext={selected}
      disabled={disabled} style={{ '--range-fill': `${100 * (value - min) / (max - min)}%` } as CSSProperties}
      onChange={(event) => change(event.target.valueAsNumber)} />
    <div className="vm-range-bounds" aria-hidden="true"><span>{lower}</span><span>{upper}</span></div>
  </div>;
}

function VmForm({ api, vm, select }: { api: VmApi; vm?: VirtualMachine; select: (id: string | null) => void }) {
  const [name, setName] = useState(vm?.name ?? 'R4OS VM');
  const [cpus, setCpus] = useState(vm?.cpus ?? 4), [memory, setMemory] = useState(vm?.memoryMiB ?? 4096);
  const [networkEnabled, setNetworkEnabled] = useState(vm?.networkEnabled ?? false);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const stopped = !vm || ['stopped', 'failed'].includes(vm.state);
  const baseImage = api.images.find((image) => image.id === api.defaultImageId);
  const blocked = busy || !stopped || !name.trim() || !api.available || (!vm && (api.loading || !baseImage || !api.networkAvailable));
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (blocked) return;
    setBusy(true); setError('');
    try { const result = await api.request<{ vm: VirtualMachine }>(vm ? `/${vm.id}` : '', vm ? 'PATCH' : 'POST', {
      name, cpus, memoryMiB: memory, ...(vm ? { networkEnabled } : { imageId: baseImage?.id }),
    });
      await api.reload(); select(result.vm.id);
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  const nameField = <><label htmlFor="vm-name">Name</label><input id="vm-name" value={name} onChange={(event) => setName(event.target.value)} required maxLength={80} disabled={busy || !stopped} /></>;
  return <form className={vm ? 'vm-form' : 'vm-form vm-create-form'} onSubmit={(event) => void submit(event)}>
    {vm ? <>{nameField}
      <label htmlFor="vm-cpus">Virtual CPUs</label><input id="vm-cpus" type="number" min={1} max={8} value={cpus} onChange={(event) => setCpus(Number(event.target.value))} required disabled={busy || !stopped} />
      <label htmlFor="vm-memory">Memory (MiB)</label><input id="vm-memory" type="number" min={2048} max={16384} step={256} value={memory} onChange={(event) => setMemory(Number(event.target.value))} required disabled={busy || !stopped} />
      <label className="vm-network" htmlFor="vm-network"><input id="vm-network" type="checkbox" checked={networkEnabled} onChange={(event) => setNetworkEnabled(event.target.checked)} disabled={busy || !stopped || (!api.networkAvailable && !networkEnabled)} />Network</label>
      <p className="vm-help">{api.networkAvailable ? 'Enable outbound networking with private NAT and DHCP. Changes apply at the next start.' : vmNetworkUnavailable}</p>
    </> : <>
      <div className="vm-range">{nameField}</div>
      <VmRange id="vm-cpus" label="Virtual CPUs" value={cpus} min={1} max={8} step={1}
        display={(value) => value === 1 ? '1 vCPU' : `${value} vCPUs`} bounds={['1', '8']} disabled={busy} change={setCpus} />
      <VmRange id="vm-memory" label="Memory" value={memory} min={2048} max={16384} step={256}
        display={(value) => `${value / 1024} GB`} disabled={busy} change={setMemory} />
      {!api.loading && !api.networkAvailable && <p className="vm-help">{vmNetworkUnavailable}</p>}
      {!api.loading && !baseImage && <p className="vm-help">Select an installed default release under Updates → R4OS Releases before creating a VM.</p>}
    </>}
    {!stopped && <p className="vm-help">Stop the VM before changing its settings.</p>}
    {error && <p className="vm-alert" role="alert">{error}</p>}
    <button className="button-primary" type="submit" disabled={blocked}>
      {busy ? 'Saving…' : vm ? 'Save settings' : 'Create virtual machine'}</button>
  </form>;
}
function Logs({ api, vm }: { api: VmApi; vm: VirtualMachine }) {
  const [kind, setKind] = useState('serial'), [text, setText] = useState(''), [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    async function load() { try { const result = await api.request<{ text: string }>(`/${vm.id}/log?name=${kind}`); if (!cancelled) { setText(result.text); setError(''); } }
      catch (cause) { if (!cancelled) setError((cause as Error).message); } }
    void load(); const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 4000);
    return () => { cancelled = true; window.clearInterval(timer); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vm.id, kind]);
  return <div><label className="vm-help">Log <select value={kind} onChange={(event) => setKind(event.target.value)}><option value="serial">Guest serial</option><option value="qemu">QEMU</option></select></label>
    {error && <p className="vm-alert">{error}</p>}<pre className="vm-log">{text || 'No log output yet.'}</pre></div>;
}
function VmDetails({ api, vm, view, select }: { api: VmApi; vm?: VirtualMachine; view: string; select: (id: string | null) => void }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [confirm, setConfirm] = useState(''), [notice, setNotice] = useState('');
  const reset = useVmReset(api, vm);
  async function action(name: string) {
    if (!vm) return; setBusy(true); setError(''); setNotice('');
    try { if (name === 'delete') { await api.request(`/${vm.id}`, 'DELETE', { confirm: true }); select(null); }
      else { await api.request(`/${vm.id}/actions`, 'POST', { action: name });
        if (name === 'shutdown') setNotice('Shutdown requested. Wait for the guest to power off. If it does not respond, use Force Stop.'); }
      setConfirm(''); await api.reload();
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  const stopped = !vm || ['stopped', 'failed'].includes(vm.state);
  const resetBlocked=reset.busy||!!reset.pending;
  return <div className="vm-shell">
    {vm && ['Overview', 'Console'].includes(view) && <div className="vm-header" aria-label="Virtual machine controls">
      <span className={`vm-status ${vm.state}`}>{vm.state}</span>
      <div className="vm-controls">
        <button className="button-primary" disabled={busy || resetBlocked || !stopped || !api.available} onClick={() => void action('start')}><Icon name="play" />Start</button>
        <button className="button-secondary" disabled={busy || resetBlocked || stopped || vm.state === 'starting' || vm.state === 'stopping'} onClick={() => setConfirm('restart')}><Icon name="restart" />Restart</button>
        <button className="button-secondary" disabled={busy || resetBlocked || stopped || vm.state === 'starting' || vm.state === 'stopping'} onClick={() => void action('shutdown')}><Icon name="power" />Shutdown</button>
        <button className="button-danger" disabled={busy || resetBlocked || stopped} onClick={() => setConfirm('force-stop')}><Icon name="stop" />Force Stop</button>
      </div>
    </div>}
    <div className={`vm-content ${view === 'Console' && vm ? 'vm-content-console' : ''}`}>
    {api.error && <p className="vm-alert" role="alert">{api.error}</p>}
    {!api.loading && !api.available && <p className="vm-alert">VM host support is not installed. See the host setup documentation.</p>}
    <section className={`vm-card ${!vm ? 'vm-card-create' : view === 'Console' ? 'vm-card-console' : view === 'Exchange' ? 'vm-card-exchange' : ''}`}>
      {!vm ? <VmForm api={api} select={select} /> : <>
        {confirm && <div className="vm-alert" role="alert"><p>{confirm === 'delete' ? 'Delete this VM, its disks and exchange files? The base image will be kept.' : confirm === 'restart' ? 'Restart this guest immediately? Unsaved guest work may be lost.' : 'Force this VM to stop? Unsaved guest work may be lost.'}</p>
          <button className="button-danger" disabled={busy || resetBlocked} onClick={() => void action(confirm)}>Confirm {confirm}</button><button className="button-secondary" disabled={busy} onClick={() => { setConfirm(''); }}>Cancel</button></div>}
        <VmResetDialog control={reset} vm={vm} />
        {reset.notice && <p className="vm-help" role="status">{reset.notice}</p>}
        {reset.error && !reset.review && <p className="vm-alert" role="alert">{reset.error}</p>}
        {reset.pending && !reset.review && <div className="vm-reset-recovery" role="status"><p>Original {reset.pending.kind} reset {reset.aborted ? 'did not complete.' : reset.busy ? 'is being checked…' : 'is unconfirmed.'}</p>
          <button type="button" className="button-secondary" disabled={reset.busy} onClick={() => void reset.read()}>Check original reset</button>
          <button type="button" className="button-secondary" disabled={reset.busy} onClick={() => void reset.retry()}>Retry same reset</button>
          {reset.aborted && <button type="button" className="button-secondary" disabled={reset.busy} onClick={reset.dismiss}>Close failed reset</button>}</div>}
        {notice && <p className="vm-help" role="status">{notice}</p>}
        {vm.shareSync?.error && view !== 'Exchange' && <p className="vm-alert" role="alert">{vm.shareSync.error}</p>}
        {(error || vm.error) && <p className="vm-alert" role="alert">{error || vm.error}</p>}
        {view === 'Console' ? <VmConsole vm={vm} api={api} /> : view === 'Exchange' ? <ExchangeExplorer key={vm.id} vm={vm} api={api} reset={reset} /> : view === 'Logs' ? <Logs vm={vm} api={api} /> : view === 'Settings' ? <>
          <fieldset className="vm-settings-fields" disabled={resetBlocked}><VmForm api={api} vm={vm} select={select} /><DevelopmentAccess api={api} vm={vm} /><ReleaseSettings api={api} vm={vm} /></fieldset><div className="vm-actions vm-settings-actions">
            <button className="button-danger" disabled={busy || resetBlocked || !stopped} onClick={() => reset.open('system')}>Reset virtual machine</button>
            <button className="button-danger" disabled={busy || resetBlocked || !stopped} onClick={() => reset.open('exchange')}>Reset Exchange Partition</button>
            <button className="button-danger" disabled={busy || resetBlocked || !stopped} onClick={() => setConfirm('delete')}>Delete virtual machine</button></div></> :
          <><dl className="vm-properties">{[['Name', vm.name], ['Base image', vm.imageId], ['Virtual CPUs', vm.cpus], ['Memory', `${vm.memoryMiB} MiB`], ['Network', vm.networkEnabled ? 'Enabled' : 'Disabled'], ['Exchange drive', 'Persistent writable FAT32'], ['Created', new Date(vm.createdAt).toLocaleString()]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
            <p className="vm-help">System and data partitions are private to this VM. The base release is shared read-only. Project assignment will be added later.</p></>}
      </>}
    </section>
  </div></div>;
}

export function VmPanel(props: Parameters<typeof VmDetails>[0]) {
  return <VmDetails key={props.vm?.id ?? 'new'} {...props} />;
}
