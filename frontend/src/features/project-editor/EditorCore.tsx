import { useLayoutEffect, useRef, useState } from 'react';
import { EditorState, Prec } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import type { EditorDocument } from './model';
import { languageName } from './languages';
import './styles.css';

function position(state: EditorState) {
  const head = state.selection.main.head, line = state.doc.lineAt(head);
  return { line: line.number, column: head - line.from + 1 };
}

export function EditorCore({ doc, readOnly, onState, save, navigated }: {
  doc: EditorDocument; readOnly: boolean; onState: (state: EditorState) => void; save: () => void;
  navigated: (navigation: EditorDocument['navigation']) => void;
}) {
  const parent = useRef<HTMLDivElement>(null), view = useRef<EditorView | null>(null);
  const callbacks = useRef({ onState, save, navigated });
  const [localCaret, setCaret] = useState(() => ({ doc, ...position(doc.state) }));
  const caret = localCaret.doc === doc ? localCaret : position(doc.state);
  useLayoutEffect(() => { callbacks.current = { onState, save, navigated }; });
  useLayoutEffect(() => {
    if (!parent.current) return;
    const initial = doc.state.update({ effects: doc.viewConfig.reconfigure([
      EditorView.contentAttributes.of({ 'aria-label': `Source code: ${doc.path}` }),
      Prec.highest(keymap.of([{ key: 'Mod-s', run: () => { callbacks.current.save(); return true; } }])),
      EditorView.updateListener.of((update) => {
        callbacks.current.onState(update.state);
        if (update.docChanged || update.selectionSet) {
          const next = position(update.state);
          setCaret(old => old.doc === doc && old.line === next.line && old.column === next.column ? old : { doc, ...next });
        }
      }),
    ]) }).state;
    const instance = new EditorView({ state: initial, parent: parent.current });
    view.current = instance;
    callbacks.current.onState(initial);
    const restoreScroll = !doc.navigation?.line;
    const frame = requestAnimationFrame(() => { if (restoreScroll) { instance.scrollDOM.scrollTop = doc.scrollTop; instance.scrollDOM.scrollLeft = doc.scrollLeft; } });
    return () => {
      cancelAnimationFrame(frame); doc.scrollTop = instance.scrollDOM.scrollTop; doc.scrollLeft = instance.scrollDOM.scrollLeft;
      instance.destroy(); view.current = null;
    };
  }, [doc]);
  useLayoutEffect(() => {
    const instance = view.current;
    if (instance && instance.state !== doc.state) instance.setState(doc.state);
  });
  useLayoutEffect(() => {
    const instance = view.current, navigation = doc.navigation;
    if (!instance || !navigation) return;
    if (navigation.line) {
      const line = instance.state.doc.line(Math.max(1, Math.min(instance.state.doc.lines, navigation.line)));
      instance.dispatch({ selection: { anchor: line.from }, effects: EditorView.scrollIntoView(line.from, { y: 'center' }) });
    }
    instance.focus();
    callbacks.current.navigated(navigation);
  }, [doc, doc.navigation]);
  useLayoutEffect(() => {
    view.current?.dispatch({ effects: doc.readOnly.reconfigure([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]) });
  }, [doc, readOnly]);
  return <><div className="editor-code" ref={parent} />
    <div className="editor-status"><span>{languageName(doc.path)}</span><span>Ln {caret.line}, Col {caret.column}</span>
      <span>UTF-8{doc.file.format?.bom ? ' BOM' : ''}</span><span>{doc.file.format?.eol?.toUpperCase()}</span>{readOnly && <span>Read only</span>}</div>
  </>;
}
