import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
const targets = new Map<Element, (visible: boolean) => void>(), visibilityListeners = new Set<() => void>();
let observer: IntersectionObserver | undefined;
const shown = () => !document.hidden;
const visibilityChanged = () => visibilityListeners.forEach(listener => listener());
function watchVisibility(listener: () => void) {
  if (!visibilityListeners.size) document.addEventListener('visibilitychange', visibilityChanged);
  visibilityListeners.add(listener);
  return () => { visibilityListeners.delete(listener); if (!visibilityListeners.size) document.removeEventListener('visibilitychange', visibilityChanged); };
}
export function useImageVisibility(enabled = true) {
  const ref = useRef<HTMLSpanElement>(null), [visible, setVisible] = useState(false);
  const showing = useSyncExternalStore(watchVisibility, shown, shown);
  useEffect(() => {
    const element = ref.current; if (!element || !enabled) return;
    observer ??= new IntersectionObserver(entries => {
      for (const entry of entries) targets.get(entry.target)?.(entry.isIntersecting);
    }, { rootMargin: '240px', threshold: 0 });
    targets.set(element, setVisible); observer.observe(element);
    return () => { observer?.unobserve(element); targets.delete(element);
      if (!targets.size) { observer?.disconnect(); observer = undefined; }
    };
  }, [enabled]);
  return { ref, visible: enabled && visible && showing };
}
