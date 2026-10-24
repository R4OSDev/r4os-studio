import { useEffect, useSyncExternalStore } from 'react';
import { editorRegistry } from './registry';

export function useEditorProject(id: string, token: string) {
  useSyncExternalStore(editorRegistry.subscribe, editorRegistry.snapshot);
  useEffect(() => { editorRegistry.activate(id, token); }, [id, token]);
  return editorRegistry.project(id);
}
