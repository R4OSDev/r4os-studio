import { useRef, useState } from 'react';
import { Icon } from '../../app/Icon';
import type { AttachmentDraft, useAttachments } from './useAttachments';
import { AttachmentStorage } from './AttachmentStorage';

type Control = ReturnType<typeof useAttachments>;
const size = (bytes: number) => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MiB` : bytes >= 1024 ? `${Math.ceil(bytes / 1024)} KiB` : `${bytes} bytes`;
export function AttachmentButton({ control, disabled }: { control: Control; disabled: boolean }) {
  const input = useRef<HTMLInputElement>(null), attach = useRef<HTMLButtonElement>(null);
  return <div className="agent-attachment-picker">
    <input ref={input} type="file" multiple hidden disabled={disabled} aria-label="Attachment files"
      accept="image/png,image/jpeg,image/webp,application/pdf,text/*,.md,.json,.csv,.log,.zig,.rs,.c,.h,.cpp,.hpp,.ts,.tsx,.js,.jsx,.py,.toml,.yaml,.yml,.r4mf,.r4af,.svg"
      onChange={event => { if (event.target.files) control.add(Array.from(event.target.files)); event.target.value = ''; }} />
    <AttachmentStorage control={control} disabled={disabled} fallback={attach} />
    <button ref={attach} type="button" className="agent-attach-files" aria-label="Attach files" title="Attach files" disabled={disabled} onClick={() => input.current?.click()}><Icon name="attachment" /></button>
  </div>;
}
function Card({ item, control, disabled }: { item: AttachmentDraft; control: Control; disabled: boolean }) {
  const [failedPreview, setFailedPreview] = useState(false), metadata = item.attachment;
  const status = item.state === 'ready' ? metadata?.readable === false ? 'Text unavailable' : 'Ready'
    : item.state === 'uploading' ? item.progress === 100 ? 'Checking file…' : `Uploading ${item.progress}%`
      : item.state === 'queued' ? 'Queued' : item.state === 'checking' ? 'Checking upload…' : 'Upload failed';
  return <li className={'agent-attachment-card ' + (item.state === 'error' || metadata?.readable === false ? 'has-error' : '')}>
    {metadata?.mode === 'localImage' && !failedPreview
      ? <img src={control.preview(metadata.id)} alt={'Preview: ' + item.name} loading="lazy" onError={() => setFailedPreview(true)} /> : <div className="agent-attachment-file"><Icon name="book" /></div>}
    <div className="agent-attachment-detail"><strong title={item.name}>{item.name}</strong>
      <span>{metadata?.mediaType ?? item.mediaType} · {size(item.size)}{metadata?.mode === 'pdfText' ? ' · Text only' : ''}</span>
      <span role="status">{status}</span>
      {item.state === 'uploading' && <progress aria-label={'Upload ' + item.name} value={item.progress} max={100} />}
      {(item.error || metadata?.limitation || failedPreview) && <p>{item.error ?? metadata?.limitation ?? 'Image preview unavailable.'}</p>}
      {(item.state === 'error' || item.state === 'checking') && <div className="agent-attachment-recovery">
        <button type="button" disabled={disabled} onClick={() => void control.checkStatus(item)}>Check status</button>
        {item.retryable && <button type="button" disabled={disabled} onClick={() => void control.checkStatus(item, true)}>Retry upload</button>}
      </div>}
    </div>
    <button type="button" className="agent-attachment-remove" aria-label={'Remove attachment ' + item.name} title="Remove this draft attachment" disabled={disabled} onClick={() => void control.remove(item)}>×</button>
  </li>;
}
export function AttachmentCards({ control, disabled }: { control: Control; disabled: boolean }) {
  return <>
    {!!control.drafts.length && <ul className="agent-attachment-list" aria-label="Selected attachments">{control.drafts.map(item => <Card key={item.requestId} item={item} control={control} disabled={disabled} />)}</ul>}
    {control.issue && <p className="agent-attachment-message" role="status">{control.issue}</p>}
    {control.error && <p className="agent-attachment-message error" role="alert">{control.error}</p>}
    {control.storedError && <p className="agent-attachment-message error" role="alert">Stored uploads could not be checked. {control.storedError}{' '}
      <button type="button" disabled={disabled} onClick={control.refreshStored}>Retry upload listing</button></p>}
  </>;
}
