export interface EditorFormat { bom: boolean; eol: 'lf' | 'crlf' | 'mixed' }
export interface EditorNode {
  path: string; name: string; kind: 'file' | 'directory' | 'link' | 'special' | 'missing';
  bytes?: number; revision?: string; sha256?: string; text?: string; format?: EditorFormat;
  editable: boolean; reason?: string;
}
export interface EditorTree { path: string; revision: string; entries: EditorNode[]; nextOffset: number | null }
export interface EditorStatus {
  writable: boolean; reason?: string; busy: boolean; maxTextBytes: number; mutations: number; files: EditorNode[];
}
