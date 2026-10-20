import { useState } from 'react';
import type { VirtualMachine, VmReleaseChange } from '../../../../shared/virtual-machines.js';
import type { VmApi } from './useVms';

export function ReleaseSettings({ api, vm }: { api: VmApi; vm: VirtualMachine }) {
  const [selected, setSelected] = useState(vm.imageId), [confirmation, setConfirmation] = useState<VmReleaseChange>();
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const stopped = ['stopped', 'failed'].includes(vm.state);
  const target = api.images.find((image) => image.id === selected);
  const current = api.images.find((image) => image.id === vm.imageId);
  const same = target?.id === vm.imageId && target?.sha256 === vm.imageSha256;
  async function change() {
    if (!confirmation) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await api.request(`/${vm.id}/release`, 'PATCH', confirmation);
      setConfirmation(undefined); await api.reload(); setNotice('R4OS release changed. C: and D: were reset. The Exchange Drive was kept.');
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  }
  return <section className="vm-release" aria-label="R4OS Release">
    <h2>R4OS Release</h2>
    <p className="vm-help">Current release: <strong>{current ? `R4OS ${current.version} Full` : vm.imageId}</strong>. Installed releases come from Updates → R4OS Releases.</p>
    <label htmlFor="vm-release">Release</label>
    <select id="vm-release" value={selected} disabled={busy || !stopped || !!confirmation} onChange={(event) => { setSelected(event.target.value); setError(''); setNotice(''); }}>
      {!current && <option value={vm.imageId}>{vm.imageId} (unavailable)</option>}
      {api.images.map((image) => <option key={image.id} value={image.id}>R4OS {image.version} Full</option>)}
    </select>
    <button type="button" className="button-secondary" disabled={!stopped || busy || !target || same || !!confirmation} onClick={() => {
      if (target) { setError(''); setNotice(''); setConfirmation({ confirm: true, expectedRevision: vm.revision ?? vm.imageSha256,
        expectedImageId: vm.imageId, expectedImageSha256: vm.imageSha256, imageId: target.id, imageSha256: target.sha256 }); }
    }}>Change release</button>
    {!stopped && <p className="vm-help">Stop the VM before changing its release.</p>}
    {confirmation && <div className="vm-alert" role="alertdialog" aria-labelledby="vm-release-warning">
      <p id="vm-release-warning">Change <strong>{vm.name}</strong> from <strong>{confirmation.expectedImageId}</strong> to <strong>{confirmation.imageId}</strong>? All changes and files on C: and D: will be deleted. The Exchange Drive will be kept. This cannot be undone.</p>
      <button type="button" className="button-danger" disabled={busy || !stopped} onClick={() => void change()}>{busy ? 'Changing release…' : 'Change release and erase C: and D:'}</button>
      <button type="button" className="button-secondary" disabled={busy} onClick={() => { setConfirmation(undefined); setError(''); }}>Cancel</button>
    </div>}
    {error && <p className="vm-alert" role="alert">{error}</p>}
    {notice && <p className="vm-help" role="status">{notice}</p>}
  </section>;
}
