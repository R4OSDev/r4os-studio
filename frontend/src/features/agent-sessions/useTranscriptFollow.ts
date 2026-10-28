import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { RefObject, WheelEvent } from 'react';
import type { SessionItem } from '../../../../shared/agent-sessions';

// One position state drives both scrolling and its visible boundary. Content
// growth is not an upward gesture; late image/layout growth uses the same latch.
export function useTranscriptFollow(logRef: RefObject<HTMLDivElement | null>, contentRef: RefObject<HTMLDivElement | null>, items: SessionItem[], enabled: boolean) {
  const active = useRef(true), previous = useRef({ top: 0, height: 0, viewport: 0 });
  const [following, setFollowing] = useState(true);
  const follow = useCallback((value: boolean) => {
    if (active.current !== value) { active.current = value; setFollowing(value); }
  }, []);
  const align = useCallback(() => {
    const element = logRef.current;
    if (!enabled || !active.current || !element) return;
    element.scrollTop = element.scrollHeight;
    previous.current = { top: element.scrollTop, height: element.scrollHeight, viewport: element.clientHeight };
  }, [enabled, logRef]);
  useLayoutEffect(() => { align(); }, [items, align]);
  useEffect(() => {
    if (!enabled || !logRef.current || !contentRef.current) return;
    const observer = new ResizeObserver(align);
    observer.observe(logRef.current); observer.observe(contentRef.current);
    return () => observer.disconnect();
  }, [enabled, align, logRef, contentRef]);
  const onScroll = useCallback(() => {
    const element = logRef.current; if (!element) return;
    const current = { top: element.scrollTop, height: element.scrollHeight, viewport: element.clientHeight };
    const bottom = current.height - current.viewport - current.top <= 1;
    const resized = current.height !== previous.current.height || current.viewport !== previous.current.viewport;
    if (current.top < previous.current.top - 0.5 && !(resized && bottom)) follow(false);
    else if (bottom) follow(true);
    else if (!resized) follow(false);
    previous.current = current;
  }, [follow, logRef]);
  const onWheel = useCallback((event: WheelEvent<HTMLDivElement>) => {
    const element = logRef.current;
    if (!element || event.deltaY >= 0 || element.scrollTop <= 0) return;
    // Inner tool-output panes scroll independently of the conversation.
    for (let node = event.target instanceof Element ? event.target : null; node && node !== element; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight
          && (node.scrollTop > 0 || ['contain', 'none'].includes(style.overscrollBehaviorY))) return;
    }
    follow(false);
  }, [follow, logRef]);
  return { following, onScroll, onWheel };
}
