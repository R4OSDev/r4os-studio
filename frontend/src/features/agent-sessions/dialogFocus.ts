import type {KeyboardEvent} from 'react';

/** Keep Tab within the active dialog, including at the browser chrome boundary. */
export function trapDialogFocus(event:KeyboardEvent<HTMLDialogElement>) {
  if(event.key!=='Tab'||event.defaultPrevented)return;
  const dialog=event.currentTarget,active=document.activeElement;
  // A nested portal's React events can bubble through its parent dialog.
  if(!dialog.contains(active))return;
  const nodes=[...dialog.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),summary,[tabindex]:not([tabindex="-1"])')]
    .filter(node=>node.tabIndex>=0&&node.getClientRects().length>0);
  const target=event.shiftKey&&active===nodes[0]?nodes[nodes.length-1]:!event.shiftKey&&active===nodes[nodes.length-1]?nodes[0]:null;
  if(target){event.preventDefault();event.stopPropagation();target.focus();}
}
