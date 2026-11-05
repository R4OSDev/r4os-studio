import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { editorRegistry } from './registry';

export function useEditorSnapshot(id: string, channel: 'metadata' | 'files' = 'metadata') {
  const subscribe = useCallback((listener: () => void) => editorRegistry.subscribe(id, channel, listener), [id, channel]);
  const snapshot = useCallback(() => editorRegistry.snapshot(id, channel), [id, channel]);
  useSyncExternalStore(subscribe, snapshot, snapshot);
}
export function useEditorProject(id: string, token: string, channel: 'metadata' | 'files' = 'metadata') {
  useEditorSnapshot(id, channel);
  useEffect(() => { editorRegistry.activate(id, token); }, [id, token]);
  return editorRegistry.project(id);
}
