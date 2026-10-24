import { Compartment, EditorState } from '@codemirror/state';
import type { Text } from '@codemirror/state';
import { history, defaultKeymap, historyKeymap, indentWithTab } from '@codemirror/commands';
import { bracketMatching, defaultHighlightStyle, foldGutter, foldKeymap, indentOnInput, syntaxHighlighting } from '@codemirror/language';
import { EditorView, drawSelection, highlightActiveLine, highlightSpecialChars, keymap, lineNumbers } from '@codemirror/view';
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search';
import type { EditorNode } from '../../../../shared/project-editor';
import { languageFor } from './languages';

export interface EditorDocument {
  projectId: string; path: string; file: EditorNode; state: EditorState; baseText: Text;
  language: Compartment; readOnly: Compartment; viewConfig: Compartment; scrollTop: number; scrollLeft: number;
  external?: EditorNode; error?: string;
}
export function isDirty(doc: EditorDocument) { return !doc.state.doc.eq(doc.baseText); }
export async function createDocument(projectId: string, file: EditorNode): Promise<EditorDocument> {
  const language = new Compartment(), readOnly = new Compartment(), viewConfig = new Compartment();
  const state = EditorState.create({ doc: file.text ?? '', extensions: [
    history(), lineNumbers(), foldGutter(), drawSelection(), highlightSpecialChars(), highlightActiveLine(),
    bracketMatching(), indentOnInput(), highlightSelectionMatches(), syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
    keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap, ...foldKeymap, indentWithTab]),
    EditorView.lineWrapping, EditorState.tabSize.of(4), language.of(await languageFor(file.path)),
    EditorState.transactionFilter.of((transaction) => transaction.newDoc.length > 524288 ? [] : transaction),
    readOnly.of([EditorState.readOnly.of(!file.editable), EditorView.editable.of(file.editable)]), viewConfig.of([]),
  ] });
  return { projectId, path: file.path, file, state, baseText: state.doc, language, readOnly, viewConfig, scrollTop: 0, scrollLeft: 0 };
}
