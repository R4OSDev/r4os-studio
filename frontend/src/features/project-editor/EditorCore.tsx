import { useLayoutEffect, useRef } from 'react';
import { EditorState, Prec } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import type { EditorDocument } from './model';
import { languageName } from './languages';
import './styles.css';

export function EditorCore({ doc, readOnly, onState, save }: {
  doc: EditorDocument; readOnly: boolean; onState: (state: EditorState) => void; save: () => void;
}) {
  const parent = useRef<HTMLDivElement>(null), view = useRef<EditorView | null>(null);
  const callbacks = useRef({ onState, save });
  const head = doc.state.selection.main.head, currentLine = doc.state.doc.lineAt(head);
  const caret = { line: currentLine.number, column: head - currentLine.from + 1 };
  useLayoutEffect(() => { callbacks.current = { onState, save }; });
  useLayoutEffect(() => {
    if (!parent.current) return;
    const initial = doc.state.update({ effects: doc.viewConfig.reconfigure([
      EditorView.contentAttributes.of({ 'aria-label': `Source code: ${doc.path}` }),
      Prec.highest(keymap.of([{ key: 'Mod-s', run: () => { callbacks.current.save(); return true; } }])),
      EditorView.updateListener.of((update) => {
        callbacks.current.onState(update.state);
      }),
    ]) }).state;
    const instance = new EditorView({ state: initial, parent: parent.current });
    view.current = instance;
    callbacks.current.onState(initial);
    const frame = requestAnimationFrame(() => { instance.scrollDOM.scrollTop = doc.scrollTop; instance.scrollDOM.scrollLeft = doc.scrollLeft; });
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
    view.current?.dispatch({ effects: doc.readOnly.reconfigure([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]) });
  }, [doc, readOnly]);
  return <><div className="editor-code" ref={parent} />
    <div className="editor-status"><span>{languageName(doc.path)}</span><span>Ln {caret.line}, Col {caret.column}</span>
      <span>UTF-8{doc.file.format?.bom ? ' BOM' : ''}</span><span>{doc.file.format?.eol?.toUpperCase()}</span>{readOnly && <span>Read only</span>}</div>
  </>;
}
