import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent, RefObject, TouchEvent, WheelEvent } from 'react';
import type { SessionItem } from '../../../../shared/agent-sessions';

// One position state drives both scrolling and its visible boundary. Content
// growth is not an upward gesture; late image/layout growth uses the same latch.
export function useTranscriptFollow(logRef: RefObject<HTMLDivElement | null>, contentRef: RefObject<HTMLDivElement | null>, items: SessionItem[], enabled: boolean) {
  const active = useRef(true), latest = useRef(true), previous = useRef({ top: 0, height: 0, viewport: 0 }), touchY = useRef<number | null>(null);
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
  const frame = useRef<number | null>(null);
  const schedule = useCallback(() => {
    if (frame.current === null) frame.current = requestAnimationFrame(() => { frame.current = null; align(); });
  }, [align]);
  useLayoutEffect(() => { schedule(); }, [items, following, schedule]);
  useEffect(() => () => { if(frame.current !== null)cancelAnimationFrame(frame.current); }, []);
  useEffect(() => {
    if (!enabled || !logRef.current || !contentRef.current) return;
    const observer = new ResizeObserver(() => {
      const element = logRef.current;
      if (element && !active.current && (element.scrollHeight !== previous.current.height || element.clientHeight !== previous.current.viewport))
        previous.current = { top: element.scrollTop, height: element.scrollHeight, viewport: element.clientHeight };
      schedule();
    });
    observer.observe(logRef.current); observer.observe(contentRef.current);
    return () => observer.disconnect();
  }, [enabled, schedule, logRef, contentRef]);
  const onScroll = useCallback(() => {
    const element = logRef.current; if (!element) return;
    const current = { top: element.scrollTop, height: element.scrollHeight, viewport: element.clientHeight };
    const bottom = current.height - current.viewport - current.top <= 2;
    const resized = current.height !== previous.current.height || current.viewport !== previous.current.viewport;
    const movedDown = current.top > previous.current.top + 0.5;
    const selection = !active.current && movedDown && bottom ? document.getSelection() : null;
    const selecting = selection && !selection.isCollapsed && selection.rangeCount && contentRef.current
      && selection.getRangeAt(0).intersectsNode(contentRef.current);
    if (!resized) {
      if (current.top < previous.current.top - 0.5) follow(false);
      else if (bottom && (active.current && latest.current || movedDown && !selecting)) follow(true);
      else if (!bottom) follow(false);
    }
    previous.current = current;
  }, [follow, logRef, contentRef]);
  const nested = useCallback((target: EventTarget | null, delta: number) => {
    const element = logRef.current;
    for (let node = target instanceof Element ? target : null; node && node !== element; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight
          && ((delta < 0 ? node.scrollTop > 0 : node.scrollTop + node.clientHeight < node.scrollHeight - 1)
            || ['contain', 'none'].includes(style.overscrollBehaviorY))) return true;
    }
    return false;
  }, [logRef]);
  const intent = useCallback((target: EventTarget | null, delta: number) => {
    const element = logRef.current;
    if (!element || !delta || nested(target, delta)) return;
    if (delta < 0 && element.scrollTop > 0) follow(false);
    else if (delta > 0 && element.scrollHeight - element.scrollTop - element.clientHeight <= 24) { follow(true); schedule(); }
  }, [follow, logRef, nested, schedule]);
  const onWheel = useCallback((event: WheelEvent<HTMLDivElement>) => {
    // Inner tool-output panes scroll independently of the conversation.
    intent(event.target, event.deltaY);
  }, [intent]);
  const onKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest('button,a,summary,input,textarea,select,[contenteditable="true"]')) return;
    const up = ['ArrowUp', 'PageUp', 'Home'].includes(event.key) || event.key === ' ' && event.shiftKey;
    const down = ['ArrowDown', 'PageDown', 'End'].includes(event.key) || event.key === ' ' && !event.shiftKey;
    if (!up && !down) return;
    if (event.key === 'End' && !nested(event.target, 1)) { event.preventDefault(); follow(true); schedule(); }
    else intent(event.target, up ? -1 : 1);
  }, [follow, intent, nested, schedule]);
  const onPointerDown = useCallback((event: PointerEvent<HTMLDivElement>) => {
    const element = logRef.current;
    if (!element || event.target !== element || event.pointerType === 'touch') return;
    const left = element.getBoundingClientRect().left + element.clientLeft;
    if (event.clientX < left || event.clientX >= left + element.clientWidth) follow(false);
  }, [follow, logRef]);
  const onTouchStart = useCallback((event: TouchEvent<HTMLDivElement>) => { touchY.current = event.touches[0]?.clientY ?? null; }, []);
  const onTouchMove = useCallback((event: TouchEvent<HTMLDivElement>) => {
    const next = event.touches[0]?.clientY;
    if (next !== undefined && touchY.current !== null) intent(event.target, touchY.current - next);
    touchY.current = next ?? null;
  }, [intent]);
  const pause = useCallback(() => {
    follow(false);
    const element = logRef.current;
    if (element) previous.current = { top: element.scrollTop, height: element.scrollHeight, viewport: element.clientHeight };
  }, [follow, logRef]);
  const resume = useCallback(() => { follow(true); schedule(); }, [follow, schedule]);
  const viewChanged = useCallback((value: boolean) => { latest.current=value;if(!value)follow(false); },[follow]);
  return { following, onScroll, onWheel, onKeyDown, onPointerDown, onTouchStart, onTouchMove, pause, resume, viewChanged };
}
