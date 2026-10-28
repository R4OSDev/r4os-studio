import { useState } from 'react';
import type { FrozenAttachment } from '../../../../shared/agent-inputs';
import { useSessionApi, sessionPath } from './api';

export function AttachmentHistory({ files, projectId, sessionId }: { files: FrozenAttachment[]; projectId: string; sessionId: string }) {
  const { base } = useSessionApi();
  return <ul className="agent-attachment-list agent-attachment-history" aria-label="Sent attachments">{files.slice(0, 8).filter(file =>
    typeof file.id === 'string' && /^[a-f0-9-]{36}$/.test(file.id) && typeof file.name === 'string').map(file =>
    <HistoryFile key={file.id} file={file} url={base + sessionPath(projectId, sessionId) + '/attachments/' + file.id} />)}</ul>;
}
function HistoryFile({ file, url }: { file: FrozenAttachment; url: string }) {
  const [failed, setFailed] = useState(false);
  return <li className="agent-attachment-card">
    {file.mode === 'localImage' && !failed && <img src={url + '/preview'} alt={'Preview: ' + file.name} loading="lazy" onError={() => setFailed(true)} />}
    <div className="agent-attachment-detail"><strong title={file.name}>{file.name}</strong>
      <span>{file.mediaType} · {Math.ceil(file.size / 1024)} KiB{file.mode === 'pdfText' ? ' · Text only' : ''}</span>
      {file.limitation && <p>{file.limitation}</p>}
      {failed && <p>Image preview unavailable.</p>}
      <a href={url + '/download'} download={file.name}>Download original</a>
    </div>
  </li>;
}
