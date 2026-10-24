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
export interface EditorMutation {
  requestId: string; kind: 'save' | 'create' | 'mkdir' | 'rename' | 'delete'; path: string;
  expected?: { revision: string; sha256?: string }; text?: string; format?: EditorFormat; target?: string; confirm?: true;
}
export interface EditorReceipt {
  requestId: string; state: 'complete' | 'rejected' | 'unknown' | 'missing';
  kind?: EditorMutation['kind']; path?: string; target?: string; node?: EditorNode; message?: string;
}
export interface EditorSearchInput { query: string; mode: 'name' | 'content'; caseSensitive?: boolean }
export interface EditorSearchEntry { path: string; revision: string; line?: number; preview?: string }
export interface EditorSearchResult {
  entries: EditorSearchEntry[]; incomplete: boolean; scannedFiles: number; scannedBytes: number;
  scannedDirectories: number; skipped: number; excluded: number;
  limits: { files: number; directories: number; entries: number; bytes: number; matches: number; seconds: number };
  excludedDirectories: string[];
}
