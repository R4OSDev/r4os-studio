/** @jsxRuntime automatic */
import { isValidElement, useState } from 'react';
import type { ReactNode } from 'react';
import Markdown from 'react-markdown';
import type { Components } from 'react-markdown';

// Render a text transcript, never a live terminal. In particular OSC 52 must
// never alter the browser clipboard or survive a user copying visible output.
/* eslint-disable no-control-regex -- This function deliberately removes ANSI and C0/C1 control bytes. */
export function transcriptText(value: string) {
  return value
    .replace(/(?:\u001b\]|\u009d)[\s\S]*?(?:\u0007|\u001b\\|\u009c|$)/g, '')
    .replace(/(?:\u001b\[|\u009b)[0-?]*[ -/]*[@-~]/g, '')
    .replace(/\u001b[ -/]*[@-Z\\-_]/g, '')
    .replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/g, '');
}

/* eslint-enable no-control-regex */

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch { /* HTTP LAN / browser policy: use the user gesture fallback. */ }
  }
  const active = document.activeElement;
  const selection = window.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
  const input = document.createElement('textarea');
  input.value = text; input.readOnly = true; input.tabIndex = -1;
  input.style.cssText = 'position:fixed;left:-10000px;top:0;opacity:0';
  document.body.append(input); input.select();
  try { if (!document.execCommand('copy')) throw new Error('Copy failed.'); }
  finally {
    input.remove();
    if (active instanceof HTMLElement && active.isConnected) active.focus({ preventScroll: true });
    if (selection) { selection.removeAllRanges(); for (const range of ranges) selection.addRange(range); }
  }
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [feedback, setFeedback] = useState({ text: '', state: '' });
  const message = feedback.text === text ? feedback.state : '';
  return <button className="agent-copy" type="button" aria-label={label} onClick={() => {
    void copyText(text).then(() => setFeedback({ text, state: 'Copied' })).catch(() => setFeedback({ text, state: 'Copy failed' }));
  }}><span aria-live="polite">{message || 'Copy'}</span></button>;
}

export function CodeBlock({ text, label = 'Copy code', language = '' }: { text: string; label?: string; language?: string }) {
  const visible = transcriptText(text);
  return <div className="agent-code-block"><div className="agent-code-bar"><span>{language}</span><CopyButton text={visible} label={label} /></div><pre><code>{visible}</code></pre></div>;
}

const components: Components = {
  pre({ children }) {
    const code = isValidElement<{ children?: ReactNode; className?: string }>(children) ? children.props : {};
    return <CodeBlock text={typeof code.children === 'string' ? code.children : ''} language={code.className?.replace(/^language-/, '').slice(0, 32)} />;
  },
  // Images are text: rendering a model message must not issue network requests.
  img({ alt }) { return <span className="agent-image-alt">{alt || 'Image'}</span>; },
  a({ href, children }) { return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>; },
};

export function MessageText({ text, markdown = false }: { text: string; markdown?: boolean }) {
  const visible = transcriptText(text);
  return markdown ? <div className="agent-message-text agent-markdown"><Markdown skipHtml components={components}>{visible}</Markdown></div>
    : <div className="agent-message-text">{visible}</div>;
}
