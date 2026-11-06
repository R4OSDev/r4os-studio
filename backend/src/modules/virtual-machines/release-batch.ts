import { createHash, randomUUID } from 'node:crypto';
import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import type { VmReleaseBatch, VmReleaseBatchView, VmReleaseTarget, VmReleaseTargetState } from '../../../../shared/virtual-machines.js';
import { lifecycleInfo, lifecycleTarget } from '../project-development/vm-lifecycle.js';
import type { LifecycleProof } from '../project-development/vm-lifecycle.js';
import { developmentHost } from '../project-development/host.js';
import { withVmLease } from '../project-development/vm-lease.js';
import { root, validId, VmError } from './paths.js';
import { privateDirectory, readJournal, saveJournal } from './journal.js';
import { recoverReleasePlan, releaseReceipt, releaseStagingSpace, verifyReleaseImage } from './release.js';
import type { ReleasePlan, VerifiedRelease } from './release.js';
import { images, VmManager } from './service.js';

const directory = join(root, 'ReleaseBatches');
const states: VmReleaseTargetState[] = ['pending', 'stopping', 'syncing', 'updating', 'updated', 'already-current', 'blocked', 'failed', 'unknown'];
const unfinished = new Set(['stopping', 'syncing', 'updating']);
const defaults = {
  lease: (id: string, work: (guard: () => void) => Promise<void>) => withVmLease(id, work, 'reset'),
  host: (value: Record<string, unknown>) => developmentHost(value),
  observe: lifecycleInfo,
  verify: verifyReleaseImage,
  delay: () => new Promise<void>(resolve => setTimeout(resolve, 1000)),
};
function path(id: string) { if (!validId(id)) throw new VmError('Invalid release batch ID.', 400); return join(directory, id + '.json'); }
function plan(batch: VmReleaseBatch, target: VmReleaseTarget): ReleasePlan {
  return { batchId: batch.requestId, requestId: target.requestId, operation: target.operation, nextRevision: target.nextRevision,
    expectedRevision: target.expectedRevision, expectedImageId: target.expectedImageId, expectedImageSha256: target.expectedImageSha256,
    imageId: batch.imageId, imageSha256: batch.imageSha256 };
}
function view(batch: VmReleaseBatch): VmReleaseBatchView {
  const counts = Object.fromEntries(states.map(state => [state, batch.targets.filter(target => target.state === state).length])) as VmReleaseBatchView['counts'];
  return { ...batch, counts };
}

/** One serial, manually confirmed VM operation; its journal is also its recovery contract. */
export class VmReleaseBatches {
  private running?: string;
  private worker?: Promise<void>;
  private closing = false;
  constructor(private manager: VmManager, private services = defaults) {}
  private async save(batch: VmReleaseBatch) { batch.updatedAt = new Date().toISOString(); await saveJournal(path(batch.requestId), batch); }
  private async read(id: string) {
    const value = await readJournal<VmReleaseBatch>(path(id));
    if (!value) throw new VmError('Original VM release batch not found.', 404);
    if (value.schema !== 1 || value.requestId !== id || !['preview', 'running', 'paused', 'complete'].includes(value.state)
      || !Array.isArray(value.targets) || value.targets.length > 32 || new Set(value.targets.map(v => v.id)).size !== value.targets.length
      || value.targets.some(v => !validId(v.id) || !validId(v.requestId) || !validId(v.operation) || !validId(v.nextRevision) || !states.includes(v.state)))
      throw new VmError('The original VM release batch needs maintenance.');
    return value;
  }
  async list() {
    await privateDirectory(directory);
    const ids = (await readdir(directory)).filter(name => name.endsWith('.json') && validId(name.slice(0, -5)));
    const batches: VmReleaseBatchView[] = [];
    for (const name of ids) batches.push(await this.get(name.slice(0, -5)));
    return batches.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
  async get(id: string) {
    return this.manager.locked('release-batch-control', async () => {
      const batch = await this.read(id);
      if (this.running !== id && (batch.state === 'running' || batch.targets.some(v => v.state === 'unknown'))) {
        for (const target of batch.targets) {
          if (!unfinished.has(target.state) && target.state !== 'unknown') continue;
          // Reconcile only the original commit journal/receipt. Target-version equality is never a receipt.
          try {
            await this.services.lease(target.id, async guard => {
              guard(); const receipt = await recoverReleasePlan(target.id, plan(batch, target));
              target.state = receipt?.state === 'complete' ? 'updated' : receipt?.state === 'aborted' ? 'failed' : 'unknown';
              if (receipt && ['complete', 'aborted'].includes(receipt.state))
                await this.services.host({ operation: 'release_settled', vmId: target.id, requestId: target.requestId });
            });
            target.reason = target.state === 'updated' ? 'Original committed release receipt recovered.'
              : target.state === 'failed' ? 'Original preparation was aborted; no release swap was committed.'
                : 'The previous worker ended without a final receipt. No shutdown or reset was replayed.';
          } catch { target.state = 'unknown'; target.reason = 'The original release outcome needs host maintenance. No action was replayed.'; }
        }
        batch.state = batch.targets.some(v => v.state === 'pending') ? 'paused' : 'complete';
        await this.save(batch);
      }
      return view(batch);
    });
  }
  async preview(input: { requestId: string; imageId: string; imageSha256: string }) {
    return this.manager.locked('release-batch-control', async () => {
      await privateDirectory(directory);
      const previous = await readJournal<VmReleaseBatch>(path(input.requestId));
      if (previous) {
        if (previous.imageId !== input.imageId || previous.imageSha256 !== input.imageSha256) throw new VmError('This batch request ID belongs to another release.');
        return view(await this.read(input.requestId));
      }
      const image = (await images()).find(v => v.id === input.imageId && v.sha256 === input.imageSha256);
      if (!image) throw new VmError('Select an installed Full release.');
      const targets: VmReleaseTarget[] = (await this.manager.list()).map(vm => ({ id: vm.id, name: vm.name,
        expectedRevision: vm.revision ?? vm.imageSha256, expectedImageId: vm.imageId, expectedImageSha256: vm.imageSha256,
        requestId: randomUUID(), operation: randomUUID(), nextRevision: randomUUID(), state: 'pending' }));
      for (const target of targets) {
        if (target.expectedImageId === image.id && target.expectedImageSha256 === image.sha256) {
          target.state = 'already-current'; target.reason = 'Already on the selected image; no reset is needed.'; continue;
        }
        try {
          await this.services.lease(target.id, async guard => {
            guard(); await this.services.host({ operation: 'release_admission', vmId: target.id, requestId: target.requestId });
          });
        } catch (error) { target.state = 'blocked'; target.reason = (error as Error).message; }
      }
      const previewDigest = createHash('sha256').update(JSON.stringify({ imageId: image.id, imageSha256: image.sha256, targets })).digest('hex');
      const stamp = new Date().toISOString();
      const batch: VmReleaseBatch = { schema: 1, requestId: input.requestId, imageId: image.id, imageSha256: image.sha256, version: image.version,
        previewDigest, createdAt: stamp, updatedAt: stamp, state: 'preview', targets };
      await this.save(batch); return view(batch);
    });
  }
  async confirm(id: string, input: { previewDigest: string; confirm: true; stopRunning: true; resetSystem: true }, resume = false) {
    return this.manager.locked('release-batch-control', async () => {
      const batch = await this.read(id);
      if (input.confirm !== true || input.stopRunning !== true || input.resetSystem !== true || input.previewDigest !== batch.previewDigest)
        throw new VmError('Confirm the original target list, graceful shutdown and C:/D: reset.', 400);
      if (this.closing) throw new VmError('Studio is shutting down. Read the original batch after reload.', 503);
      if (this.running && this.running !== id) throw new VmError('Another VM release batch is running.');
      if (batch.state !== (resume ? 'paused' : 'preview')) return view(batch);
      if (!resume) {
        const current = await this.manager.list();
        if (current.length !== batch.targets.length || batch.targets.some(target => !current.some(vm => vm.id === target.id
          && (vm.revision ?? vm.imageSha256) === target.expectedRevision && vm.imageId === target.expectedImageId && vm.imageSha256 === target.expectedImageSha256)))
          throw new VmError('The VM list or a source revision changed. Cancel and prepare a new preview.');
      }
      const support = await this.services.host({ operation: 'capabilities' }) as { features?: { vmReleaseBatch?: number } };
      if (support.features?.vmReleaseBatch !== 1) throw new VmError('Wait for the development coordinator to adopt this Studio release.', 503);
      if (!resume) for (const target of batch.targets) { target.state = 'pending'; delete target.reason; }
      batch.consent = { confirm: true, stopRunning: true, resetSystem: true }; batch.state = 'running';
      await this.save(batch); this.running = id;
      this.worker = this.run(batch).catch(() => {
        // A failed durable write leaves the original journal recoverable; never
        // advertise an in-memory completion or replay its uncertain step.
      }).finally(() => { this.running = undefined; this.worker = undefined; });
      // All long work is below the durable acceptance. HTTP never waits for a VM stop or a disk hash.
      return view(batch);
    });
  }
  private async run(batch: VmReleaseBatch) {
    let verified: VerifiedRelease | undefined;
    try {
      if (!batch.targets.some(target => target.state === 'pending')) return;
      const image = (await images()).find(v => v.id === batch.imageId && v.sha256 === batch.imageSha256);
      if (!image) throw new VmError('The selected Full release is no longer installed.');
      await releaseStagingSpace();
      verified = await this.services.verify(image);
      for (const target of batch.targets) {
        if (target.state !== 'pending' || this.closing) continue;
        try { await verified.assert(); }
        catch { throw new VmError('The verified target image changed. Remaining targets were held.'); }
        await this.update(batch, target, verified);
      }
    } catch (error) {
      for (const target of batch.targets) if (target.state === 'pending') { target.state = 'blocked'; target.reason = (error as Error).message; }
    } finally {
      batch.state = batch.targets.some(v => v.state === 'pending') ? 'paused' : 'complete';
      await this.save(batch);
    }
  }
  private async update(batch: VmReleaseBatch, target: VmReleaseTarget, verified: VerifiedRelease) {
    let powerIntent = false, swapping = false;
    try {
      const config = await this.manager.config(target.id);
      if ((config.revision ?? config.imageSha256) !== target.expectedRevision || config.imageId !== target.expectedImageId || config.imageSha256 !== target.expectedImageSha256)
        throw new VmError('The VM changed after confirmation. Its disk was preserved.');
      if (config.imageId === batch.imageId && config.imageSha256 === batch.imageSha256) {
        target.state = 'already-current'; target.reason = 'Already on the selected image; disk and revision preserved.'; await this.save(batch); return;
      }
      await this.services.lease(target.id, async guard => {
        try {
          guard(); await this.services.host({ operation: 'release_admission', vmId: target.id, requestId: target.requestId });
          const expected = { vmRevision: target.expectedRevision, imageId: target.expectedImageId, imageSha256: target.expectedImageSha256 };
          let proof: LifecycleProof = { kind: 'vm_stop', phase: 'observing' };
          let observed = await this.services.observe(this.manager, target.id, proof);
          lifecycleTarget(observed.vm, expected);
          if (observed.vm.imageId === batch.imageId && observed.vm.imageSha256 === batch.imageSha256) {
            target.state = 'already-current'; target.reason = 'Already on the selected image; disk and revision preserved.'; await this.save(batch); return;
          }
          if (observed.vm.state === 'running' || observed.vm.state === 'paused') {
            if (!observed.process || observed.unit.controlPid !== '0' || !observed.unit.invocationId) throw new VmError('The running VM identity is not stable.');
            proof = { ...proof, phase: 'shutdown_intent', original: { unit: observed.unit, process: observed.process, bootId: observed.unit.invocationId } };
            await this.manager.action(target.id, 'shutdown', async () => {
              guard(); await this.services.host({ operation: 'release_admission', vmId: target.id, requestId: target.requestId });
              const current = await this.services.observe(this.manager, target.id, proof); lifecycleTarget(current.vm, expected);
              if (current.unit.invocationId !== proof.original!.unit.invocationId || current.process?.pid !== proof.original!.process.pid
                || current.process?.birth !== proof.original!.process.birth || current.unit.controlPid !== '0') throw new VmError('VM process changed before shutdown.');
              proof.shutdownIntentAt = new Date().toISOString(); powerIntent = true; target.state = 'stopping'; await this.save(batch);
              await this.services.host({ operation: 'release_unknown', vmId: target.id, requestId: target.requestId });
            });
            const deadline = Date.now() + 900_000;
            while (true) {
              guard(); observed = await this.services.observe(this.manager, target.id, proof); lifecycleTarget(observed.vm, expected);
              if (observed.fullyStopped && !observed.originalProcessAlive && observed.exportComplete) break;
              if (observed.fullyStopped && !observed.originalProcessAlive && observed.vm.shareSync?.error) throw new VmError(observed.vm.shareSync.error);
              if (Date.now() >= deadline || this.closing) throw new VmError('Original VM shutdown/export has no confirmed end. No force stop was sent.');
              if (observed.fullyStopped && target.state !== 'syncing') { target.state = 'syncing'; await this.save(batch); }
              await this.services.delay();
            }
          } else if (!observed.fullyStopped) throw new VmError('Wait for the VM transition and export worker to finish.');
          target.state = 'syncing'; await this.save(batch);
          guard(); await this.services.host({ operation: 'release_admission', vmId: target.id, requestId: target.requestId });
          target.state = 'updating'; await this.save(batch); swapping = true;
          await this.services.host({ operation: 'release_unknown', vmId: target.id, requestId: target.requestId });
          await this.manager.changeRelease(target.id, { confirm: true, ...plan(batch, target) }, {
            plan: plan(batch, target), verified, beforeCommit: async () => {
              guard(); await this.services.host({ operation: 'release_admission', vmId: target.id, requestId: target.requestId });
              const end = await this.services.observe(this.manager, target.id, proof); lifecycleTarget(end.vm, expected);
              if (!end.fullyStopped || end.originalProcessAlive || !end.exportComplete) throw new VmError('VM process/export changed before the release commit.');
            },
          });
          const receipt = await releaseReceipt(target.id, plan(batch, target));
          if (receipt?.state !== 'complete') throw new VmError('The original release swap has no final receipt.');
          await this.services.host({ operation: 'release_settled', vmId: target.id, requestId: target.requestId });
          powerIntent = false; target.state = 'updated'; target.reason = 'Original release commit confirmed. VM remains off; Exchange preserved.';
          await this.save(batch);
        } catch (error) {
          if (swapping) {
            const receipt = await releaseReceipt(target.id, plan(batch, target)).catch(() => undefined);
            if (receipt && ['complete', 'aborted'].includes(receipt.state))
              await this.services.host({ operation: 'release_settled', vmId: target.id, requestId: target.requestId }).catch(() => {});
          }
          if (powerIntent && !swapping) {
            // Close new guest work before releasing this very same maintenance lease.
            await this.services.host({ operation: 'release_unknown', vmId: target.id, requestId: target.requestId });
          }
          throw error;
        }
      });
    } catch (error) {
      if (swapping) {
        try {
          const receipt = await releaseReceipt(target.id, plan(batch, target));
          target.state = receipt?.state === 'complete' ? 'updated' : receipt?.state === 'aborted' ? 'failed' : 'unknown';
        } catch { target.state = 'unknown'; }
      } else target.state = powerIntent ? 'unknown' : 'blocked';
      target.reason = target.state === 'updated' ? 'Original committed release receipt confirmed after response loss.' : (error as Error).message;
      await this.save(batch);
    }
  }
  async close() { this.closing = true; await this.worker; }
}
